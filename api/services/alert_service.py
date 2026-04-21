"""
MangoPoint API — Alert Service
================================
Handles alert generation, logging, and notification dispatch.
"""

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Sequence, Tuple
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from ..core.config import settings
from db.models import Alert, AlertSeverity, AlertStatus
from ..models.schemas import AlertCreate, AlertResponse, AlertSeverityEnum
from .notification_service import notification_service
from utils.datetime_utils import format_rfc3339, utcnow_naive

logger = logging.getLogger(__name__)


class AlertService:
    """
    Service for managing pest risk alerts.
    
    Responsibilities:
    - Generate alerts when risk exceeds threshold in unbagged zones
    - Log alerts to database
    - Trigger notifications (email, SMS)
    """
    
    def __init__(self):
        self.risk_threshold = settings.ALERT_RISK_THRESHOLD
        # In-memory alert store for when database is unavailable
        self._memory_alerts: List[Dict[str, Any]] = []
    
    def store_alert_in_memory(self, alert_data: "AlertCreate") -> None:
        """Store alert in memory when database is unavailable."""
        self._memory_alerts.append({
            "alert_id": alert_data.alert_id,
            "simulation_run_id": alert_data.simulation_run_id,
            "triggered_at": format_rfc3339(utcnow_naive()),
            "severity": alert_data.severity.value if hasattr(alert_data.severity, 'value') else str(alert_data.severity),
            "status": "active",
            "risk_value": alert_data.risk_value,
            "affected_cells": alert_data.affected_cells,
            "affected_tree_ids": alert_data.affected_tree_ids,
            "orchard_id": alert_data.orchard_id,
            "zone_name": alert_data.zone_name,
            "message": alert_data.message,
            "centroid_lon": alert_data.centroid_lon,
            "centroid_lat": alert_data.centroid_lat,
            "email_sent": False,
            "sms_sent": False,
            "acknowledged_by": None,
            "acknowledged_at": None,
            "resolved_at": None,
        })
        logger.info(f"Stored alert {alert_data.alert_id} in memory (database unavailable)")
    
    def get_memory_alerts(self, status: Optional[str] = None) -> Tuple[List[Dict[str, Any]], int, int]:
        """Get alerts from memory store."""
        alerts = self._memory_alerts
        if status:
            alerts = [a for a in alerts if a["status"] == status]
        active_count = len([a for a in self._memory_alerts if a["status"] == "active"])
        return alerts, len(alerts), active_count
    
    def clear_memory_alerts(self) -> None:
        """Clear in-memory alerts."""
        self._memory_alerts = []
    
    def check_for_alerts(
        self,
        risk_grid: Any,  # numpy array
        state_grid: Any,  # numpy array
        tree_ids: Any,  # numpy array
        orchard_id: str,
        simulation_run_id: Optional[str] = None,
        cell_state_unbagged: int = 1,  # CellState.UNBAGGED
    ) -> List[AlertCreate]:
        """
        Check simulation results for alert conditions.
        
        An alert is triggered when:
        - Risk > threshold (default 0.75)
        - Cell is UNBAGGED (not protected by bagging)
        
        Parameters
        ----------
        risk_grid : np.ndarray
            2D array of risk values [0, 1]
        state_grid : np.ndarray
            2D array of cell states
        tree_ids : np.ndarray
            2D array of tree IDs
        orchard_id : str
            Identifier of the orchard
        simulation_run_id : str, optional
            Associated simulation run
        cell_state_unbagged : int
            Integer value for UNBAGGED state
            
        Returns
        -------
        list[AlertCreate]
            List of alerts to create
        """
        import numpy as np
        
        alerts = []
        
        # Find high-risk unbagged cells
        high_risk_unbagged = (risk_grid >= self.risk_threshold) & (state_grid == cell_state_unbagged)
        
        if not high_risk_unbagged.any():
            return alerts
        
        # Get indices of affected cells
        affected_indices = np.argwhere(high_risk_unbagged)
        max_risk = float(risk_grid[high_risk_unbagged].max())
        
        # Collect affected cells and tree IDs
        affected_cells = []
        affected_tree_ids = []
        
        for row, col in affected_indices:
            affected_cells.append({"row": int(row), "col": int(col)})
            tid = tree_ids[row, col]
            if tid and tid != "":
                affected_tree_ids.append(str(tid))
        
        # Determine severity based on risk level and number of affected cells
        n_affected = len(affected_cells)
        if max_risk >= 0.95 or n_affected > 50:
            severity = AlertSeverityEnum.CRITICAL
        elif max_risk >= 0.85 or n_affected > 20:
            severity = AlertSeverityEnum.HIGH
        elif max_risk >= 0.75 or n_affected > 10:
            severity = AlertSeverityEnum.MEDIUM
        else:
            severity = AlertSeverityEnum.LOW
        
        # Create alert
        alert = AlertCreate(
            alert_id=f"alert_{uuid.uuid4().hex[:12]}",
            simulation_run_id=simulation_run_id,
            severity=severity,
            risk_value=max_risk,
            affected_cells=affected_cells,
            affected_tree_ids=affected_tree_ids,
            orchard_id=orchard_id,
            zone_name=f"Zone with {n_affected} high-risk trees",
            message=self._generate_alert_message(
                severity=severity,
                n_affected=n_affected,
                max_risk=max_risk,
                orchard_id=orchard_id,
            ),
            centroid_lon=None,  # Could compute from grid
            centroid_lat=None,
        )
        
        alerts.append(alert)
        logger.warning(
            f"Alert generated: {severity.value} risk ({max_risk:.2f}) "
            f"affecting {n_affected} cells in {orchard_id}"
        )
        
        return alerts
    
    def _generate_alert_message(
        self,
        severity: AlertSeverityEnum,
        n_affected: int,
        max_risk: float,
        orchard_id: str,
    ) -> str:
        """Generate human-readable alert message."""
        severity_text = {
            AlertSeverityEnum.LOW: "Low",
            AlertSeverityEnum.MEDIUM: "Moderate",
            AlertSeverityEnum.HIGH: "High",
            AlertSeverityEnum.CRITICAL: "CRITICAL",
        }
        
        return (
            f"{severity_text[severity]} pest risk alert for orchard '{orchard_id}'. "
            f"{n_affected} unbagged tree(s) at risk with maximum probability of {max_risk:.1%}. "
            f"Immediate inspection and bagging recommended."
        )
    
    async def create_alert(
        self,
        db: AsyncSession,
        alert_data: AlertCreate,
        send_notifications: bool = True,
    ) -> Alert:
        """
        Create and persist an alert to the database.
        
        Parameters
        ----------
        db : AsyncSession
            Database session
        alert_data : AlertCreate
            Alert data to persist
        send_notifications : bool
            Whether to send email/SMS notifications
            
        Returns
        -------
        Alert
            Created alert record
        """
        alert = Alert(
            alert_id=alert_data.alert_id,
            simulation_run_id=alert_data.simulation_run_id,
            triggered_at=utcnow_naive(),
            severity=alert_data.severity,
            status=AlertStatus.ACTIVE,
            risk_value=alert_data.risk_value,
            affected_cells=alert_data.affected_cells,
            affected_tree_ids=alert_data.affected_tree_ids,
            orchard_id=alert_data.orchard_id,
            zone_name=alert_data.zone_name,
            message=alert_data.message,
            centroid_lon=alert_data.centroid_lon,
            centroid_lat=alert_data.centroid_lat,
        )
        
        db.add(alert)
        await db.flush()
        
        # Send notifications
        if send_notifications:
            await self._send_notifications(alert)
        
        logger.info(f"Alert {alert.alert_id} created and persisted")
        return alert
    
    async def _send_notifications(self, alert: Alert) -> None:
        """Send email and SMS notifications for an alert."""
        message = alert.message or "High risk alert detected"
        
        # Email notification
        try:
            email_sent = await notification_service.send_email_alert(
                subject=f"[MangoPoint] {alert.severity.value.upper()} Risk Alert",
                message=message,
                alert_id=alert.alert_id,
            )
            if email_sent:
                alert.email_sent = True
                alert.email_sent_at = utcnow_naive()
                logger.info(f"Email notification sent for alert {alert.alert_id}")
        except Exception as e:
            logger.error(f"Failed to send email for alert {alert.alert_id}: {e}")
        
        # SMS notification (stub)
        try:
            sms_sent = await notification_service.send_sms_alert(
                message=message[:160],  # SMS limit
                alert_id=alert.alert_id,
            )
            if sms_sent:
                alert.sms_sent = True
                alert.sms_sent_at = utcnow_naive()
                logger.info(f"SMS notification sent for alert {alert.alert_id}")
        except Exception as e:
            logger.error(f"Failed to send SMS for alert {alert.alert_id}: {e}")
    
    async def get_alerts(
        self,
        db: AsyncSession,
        status: Optional[AlertStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[Sequence[Alert], int, int]:
        """
        Retrieve alerts from database.
        
        Returns
        -------
        tuple
            (alerts, total_count, active_count)
        """
        query = select(Alert).order_by(Alert.triggered_at.desc())
        
        if status:
            query = query.where(Alert.status == status)
        
        query = query.limit(limit).offset(offset)
        
        result = await db.execute(query)
        alerts = result.scalars().all()
        
        # Get counts
        total_result = await db.execute(select(Alert))
        total_count = len(total_result.scalars().all())
        
        active_result = await db.execute(
            select(Alert).where(Alert.status == AlertStatus.ACTIVE)
        )
        active_count = len(active_result.scalars().all())
        
        return alerts, total_count, active_count
    
    async def acknowledge_alert(
        self,
        db: AsyncSession,
        alert_id: str,
        acknowledged_by: str,
        notes: Optional[str] = None,
    ) -> Optional[Alert]:
        """Acknowledge an alert."""
        result = await db.execute(
            select(Alert).where(Alert.alert_id == alert_id)
        )
        alert = result.scalar_one_or_none()
        
        if alert:
            alert.status = AlertStatus.ACKNOWLEDGED
            alert.acknowledged_by = acknowledged_by
            alert.acknowledged_at = utcnow_naive()
            if notes:
                alert.resolution_notes = notes
            await db.flush()
            logger.info(f"Alert {alert_id} acknowledged by {acknowledged_by}")
        
        return alert
    
    async def resolve_alert(
        self,
        db: AsyncSession,
        alert_id: str,
        resolution_notes: Optional[str] = None,
    ) -> Optional[Alert]:
        """Resolve an alert."""
        result = await db.execute(
            select(Alert).where(Alert.alert_id == alert_id)
        )
        alert = result.scalar_one_or_none()
        
        if alert:
            alert.status = AlertStatus.RESOLVED
            alert.resolved_at = utcnow_naive()
            if resolution_notes:
                alert.resolution_notes = resolution_notes
            await db.flush()
            logger.info(f"Alert {alert_id} resolved")
        
        return alert


# Singleton instance
alert_service = AlertService()
