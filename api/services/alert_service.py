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
from ..models.schemas import AlertActionStatusEnum, AlertCreate, AlertResponse, AlertSeverityEnum
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
        for alert in self._memory_alerts:
            if (
                alert.get("status") == "active"
                and alert.get("orchard_id") == alert_data.orchard_id
                and alert.get("zone_name") == alert_data.zone_name
                and alert.get("message") == alert_data.message
            ):
                logger.info(
                    "Skipped duplicate in-memory active alert for orchard %s zone %s",
                    alert_data.orchard_id,
                    alert_data.zone_name,
                )
                return

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
            "recommended_actions": alert_data.recommended_actions or [],
            "action_status": (
                alert_data.action_status.value
                if hasattr(alert_data.action_status, "value")
                else str(alert_data.action_status or "pending")
            ),
            "action_assigned_to": alert_data.action_assigned_to,
            "action_notes": alert_data.action_notes,
            "action_due_at": (
                format_rfc3339(alert_data.action_due_at)
                if alert_data.action_due_at
                else None
            ),
            "action_completed_at": (
                format_rfc3339(alert_data.action_completed_at)
                if alert_data.action_completed_at
                else None
            ),
            "email_sent": False,
            "sms_sent": False,
            "acknowledged_by": None,
            "acknowledged_at": None,
            "resolved_at": None,
        })
        logger.info(f"Stored alert {alert_data.alert_id} in memory (database unavailable)")
    
    def get_memory_alerts(
        self,
        status: Optional[str] = None,
        orchard_id: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], int, int]:
        """Get alerts from memory store."""
        alerts = self._memory_alerts
        if status:
            alerts = [a for a in alerts if a["status"] == status]
        if orchard_id:
            alerts = [a for a in alerts if a.get("orchard_id") == orchard_id]

        active_alerts = [
            a for a in self._memory_alerts
            if a["status"] == "active"
        ]
        if orchard_id:
            active_alerts = [
                a for a in active_alerts
                if a.get("orchard_id") == orchard_id
            ]
        active_count = len(active_alerts)
        return alerts, len(alerts), active_count
    
    def clear_memory_alerts(self) -> None:
        """Clear in-memory alerts."""
        self._memory_alerts = []

    def update_memory_alert(
        self,
        alert_id: str,
        **updates: Any,
    ) -> Optional[Dict[str, Any]]:
        """Update an in-memory fallback alert."""
        for alert in self._memory_alerts:
            if alert["alert_id"] == alert_id:
                alert.update({
                    key: value
                    for key, value in updates.items()
                    if value is not None
                })
                return alert
        return None
    
    def check_for_alerts(
        self,
        risk_grid: Any,  # numpy array
        state_grid: Any,  # numpy array
        tree_ids: Any,  # numpy array
        orchard_id: str,
        simulation_run_id: Optional[str] = None,
        cell_state_unbagged: int = 1,  # CellState.UNBAGGED
        risk_threshold: Optional[float] = None,
        lon_grid: Optional[Any] = None,  # numpy array
        lat_grid: Optional[Any] = None,  # numpy array
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
        risk_threshold : float, optional
            Alert threshold for this simulation. Defaults to service setting.
        lon_grid, lat_grid : np.ndarray, optional
            2D arrays of cell centroid coordinates for map markers.
            
        Returns
        -------
        list[AlertCreate]
            List of alerts to create
        """
        import numpy as np
        
        alerts = []
        threshold = self.risk_threshold if risk_threshold is None else float(risk_threshold)
        
        # Find high-risk unbagged cells
        high_risk_unbagged = (risk_grid >= threshold) & (state_grid == cell_state_unbagged)
        
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
        
        n_affected = len(affected_cells)
        severity = self._classify_severity(max_risk, n_affected)

        centroid_lon = None
        centroid_lat = None
        if lon_grid is not None and lat_grid is not None:
            try:
                lons = lon_grid[high_risk_unbagged]
                lats = lat_grid[high_risk_unbagged]
                valid = np.isfinite(lons) & np.isfinite(lats)
                if valid.any():
                    centroid_lon = float(lons[valid].mean())
                    centroid_lat = float(lats[valid].mean())
            except Exception:
                centroid_lon = None
                centroid_lat = None
        
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
                risk_threshold=threshold,
            ),
            centroid_lon=centroid_lon,
            centroid_lat=centroid_lat,
            recommended_actions=self._recommended_actions(
                alert_kind="risk",
                n_affected=n_affected,
            ),
        )
        
        alerts.append(alert)
        logger.warning(
            f"Alert generated: {severity.value} risk ({max_risk:.2f}) "
            f"affecting {n_affected} cells in {orchard_id}"
        )
        
        return alerts

    def check_tree_feature_alerts(
        self,
        features: Sequence[Dict[str, Any]],
        orchard_id: str,
        simulation_run_id: Optional[str] = None,
        risk_threshold: Optional[float] = None,
    ) -> List[AlertCreate]:
        """
        Check point-based tree simulation output for alert conditions.

        Tree-graph simulations emit GeoJSON Point features rather than row/col
        grid cells. An alert is triggered when a susceptible tree point is at or
        above the configured risk threshold.
        """
        affected_tree_ids: List[str] = []
        affected_lons: List[float] = []
        affected_lats: List[float] = []
        affected_risks: List[float] = []
        threshold = self.risk_threshold if risk_threshold is None else float(risk_threshold)

        susceptible_states = {"unbagged", "susceptible", "healthy"}

        for feature in features:
            props = feature.get("properties", {}) or {}

            try:
                risk = float(props.get("risk", 0.0) or 0.0)
            except (TypeError, ValueError):
                continue

            if risk < threshold:
                continue

            state = str(props.get("state", "")).strip().lower()
            if state not in susceptible_states:
                continue

            tree_id = self._feature_tree_id(props)
            if tree_id is not None:
                affected_tree_ids.append(tree_id)

            lon_lat = self._point_coordinates(feature)
            if lon_lat is not None:
                lon, lat = lon_lat
                affected_lons.append(lon)
                affected_lats.append(lat)

            affected_risks.append(risk)

        if not affected_risks:
            return []

        max_risk = max(affected_risks)
        n_affected = len(affected_risks)
        severity = self._classify_severity(max_risk, n_affected)

        centroid_lon = sum(affected_lons) / len(affected_lons) if affected_lons else None
        centroid_lat = sum(affected_lats) / len(affected_lats) if affected_lats else None

        alert = AlertCreate(
            alert_id=f"alert_{uuid.uuid4().hex[:12]}",
            simulation_run_id=simulation_run_id,
            severity=severity,
            risk_value=max_risk,
            affected_cells=[],
            affected_tree_ids=affected_tree_ids,
            orchard_id=orchard_id,
            zone_name=f"Tree zone with {n_affected} high-risk trees",
            message=self._generate_alert_message(
                severity=severity,
                n_affected=n_affected,
                max_risk=max_risk,
                orchard_id=orchard_id,
                risk_threshold=threshold,
            ),
            centroid_lon=centroid_lon,
            centroid_lat=centroid_lat,
            recommended_actions=self._recommended_actions(
                alert_kind="risk",
                n_affected=n_affected,
            ),
        )

        logger.warning(
            f"Tree alert generated: {severity.value} risk ({max_risk:.2f}) "
            f"affecting {n_affected} tree points in {orchard_id}"
        )

        return [alert]

    def check_gate_condition_alerts(
        self,
        diagnostics: Optional[Sequence[Dict[str, Any]]],
        orchard_id: str,
        simulation_run_id: Optional[str] = None,
        pest_type: Optional[str] = None,
        orchard_stage: Optional[str] = None,
    ) -> List[AlertCreate]:
        """
        Create a condition alert when the pest biological gate opens.

        This alert is intentionally separate from the spatial risk alert. It
        tells the grower that weather and crop-stage conditions are favorable
        for pest activity, even before the simulation output identifies a
        specific high-risk tree cluster.
        """
        if not diagnostics:
            return []

        total_hours = len(diagnostics)
        open_entries = [
            entry for entry in diagnostics
            if bool(entry.get("gate_open"))
        ]
        if not open_entries:
            return []

        open_count = len(open_entries)
        open_fraction = open_count / total_hours if total_hours else 0.0
        severity = self._classify_gate_condition_severity(
            open_count=open_count,
            open_fraction=open_fraction,
        )
        pest_label = self._pest_label(pest_type)
        first_window = self._gate_window_label(open_entries[0])
        stage_text = (
            str(orchard_stage).replace("_", " ").title()
            if orchard_stage
            else "Current"
        )

        alert = AlertCreate(
            alert_id=f"alert_gate_{uuid.uuid4().hex[:12]}",
            simulation_run_id=simulation_run_id,
            severity=severity,
            risk_value=open_fraction,
            affected_cells=[],
            affected_tree_ids=[],
            orchard_id=orchard_id,
            zone_name=f"{pest_label} gate condition",
            message=(
                f"{pest_label} biological gate opened for {open_count} of "
                f"{total_hours} forecast hour(s) in orchard '{orchard_id}'. "
                f"First favorable window: {first_window}. "
                f"Stage: {stage_text}. Inspect the orchard and review the "
                f"simulation map before treatment decisions."
            ),
            centroid_lon=None,
            centroid_lat=None,
            recommended_actions=self._recommended_actions(
                alert_kind="condition",
                pest_type=pest_type,
            ),
        )

        logger.warning(
            "Gate condition alert generated: %s gate open for %d/%d hours in %s",
            pest_label,
            open_count,
            total_hours,
            orchard_id,
        )

        return [alert]

    def _classify_severity(
        self,
        max_risk: float,
        n_affected: int,
    ) -> AlertSeverityEnum:
        """Classify alert severity from peak risk and affected tree count."""
        if max_risk >= 0.95 or n_affected > 50:
            return AlertSeverityEnum.CRITICAL
        if max_risk >= 0.85 or n_affected > 20:
            return AlertSeverityEnum.HIGH
        if max_risk >= 0.75 or n_affected > 10:
            return AlertSeverityEnum.MEDIUM
        return AlertSeverityEnum.LOW

    @staticmethod
    def _classify_gate_condition_severity(
        open_count: int,
        open_fraction: float,
    ) -> AlertSeverityEnum:
        """Classify condition severity from favorable forecast duration."""
        if open_count >= 6 or open_fraction >= 0.50:
            return AlertSeverityEnum.HIGH
        if open_count >= 3 or open_fraction >= 0.25:
            return AlertSeverityEnum.MEDIUM
        return AlertSeverityEnum.LOW

    @staticmethod
    def _pest_label(pest_type: Optional[str]) -> str:
        """Convert pest identifiers to farmer-readable labels."""
        value = str(pest_type or "").strip().lower().replace("-", "_")
        if value in {"cecid", "cecid_fly", "cecid fly"}:
            return "Cecid fly"
        if value in {"fruitfly", "fruit_fly", "fruit fly"}:
            return "Fruit fly"
        if not value:
            return "Pest"
        return value.replace("_", " ").title()

    @staticmethod
    def _gate_window_label(entry: Dict[str, Any]) -> str:
        """Return a compact label for the first favorable forecast hour."""
        dt_value = entry.get("datetime")
        if dt_value:
            return str(dt_value)

        step = entry.get("step")
        if step is not None:
            return f"forecast step {step}"

        return "forecast period"

    def _recommended_actions(
        self,
        alert_kind: str,
        pest_type: Optional[str] = None,
        n_affected: int = 0,
    ) -> List[str]:
        """Generate practical response steps for farmer-facing alert workflow."""
        pest_label = self._pest_label(pest_type).lower()

        if alert_kind == "condition":
            if "cecid" in pest_label:
                return [
                    "Inspect fruitlet-stage blocks during the next dawn or dusk activity window.",
                    "Check recent rain-affected low areas and canopy interiors for cecid fly symptoms.",
                    "Record field observations before deciding on treatment.",
                ]
            if "fruit fly" in pest_label:
                return [
                    "Inspect mature fruit blocks and check traps during the favorable activity window.",
                    "Remove fallen or damaged fruit and prioritize sanitation around flagged blocks.",
                    "Review the simulator map before applying any targeted control action.",
                ]
            return [
                "Inspect susceptible orchard blocks during the favorable weather window.",
                "Record observations and review simulator output before treatment decisions.",
            ]

        scope = f"{n_affected} flagged tree(s)" if n_affected else "flagged trees"
        return [
            f"Inspect {scope} and nearby susceptible trees within the alert zone.",
            "Confirm pest signs in the field and submit an observation record.",
            "Prioritize bagging, sanitation, or targeted treatment based on confirmed pest pressure.",
        ]

    @staticmethod
    def _feature_tree_id(props: Dict[str, Any]) -> Optional[str]:
        """Extract a stable tree identifier from common property names."""
        for key in ("tree_id", "Tree_ID", "id", "fid"):
            value = props.get(key)
            if value is not None and value != "":
                return str(value)
        return None

    @staticmethod
    def _point_coordinates(feature: Dict[str, Any]) -> Optional[Tuple[float, float]]:
        """Return ``(lon, lat)`` for a GeoJSON Point feature if available."""
        geometry = feature.get("geometry", {}) or {}
        if geometry.get("type") != "Point":
            return None

        coordinates = geometry.get("coordinates", [])
        if not isinstance(coordinates, (list, tuple)) or len(coordinates) < 2:
            return None

        try:
            return float(coordinates[0]), float(coordinates[1])
        except (TypeError, ValueError):
            return None
    
    def _generate_alert_message(
        self,
        severity: AlertSeverityEnum,
        n_affected: int,
        max_risk: float,
        orchard_id: str,
        risk_threshold: Optional[float] = None,
    ) -> str:
        """Generate human-readable alert message."""
        severity_text = {
            AlertSeverityEnum.LOW: "Low",
            AlertSeverityEnum.MEDIUM: "Moderate",
            AlertSeverityEnum.HIGH: "High",
            AlertSeverityEnum.CRITICAL: "CRITICAL",
        }
        
        threshold_text = (
            f" Alert threshold: {risk_threshold:.0%}."
            if risk_threshold is not None
            else ""
        )
        return (
            f"{severity_text[severity]} pest risk alert for orchard '{orchard_id}'. "
            f"{n_affected} unbagged tree(s) at risk with maximum probability of {max_risk:.1%}. "
            f"Immediate inspection and bagging recommended."
            f"{threshold_text}"
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
        severity_value = (
            alert_data.severity.value
            if hasattr(alert_data.severity, "value")
            else str(alert_data.severity)
        )

        alert = Alert(
            alert_id=alert_data.alert_id,
            simulation_run_id=alert_data.simulation_run_id,
            triggered_at=utcnow_naive(),
            severity=AlertSeverity(severity_value),
            status=AlertStatus.ACTIVE,
            risk_value=alert_data.risk_value,
            affected_cells=alert_data.affected_cells,
            affected_tree_ids=alert_data.affected_tree_ids,
            orchard_id=alert_data.orchard_id,
            zone_name=alert_data.zone_name,
            message=alert_data.message,
            centroid_lon=alert_data.centroid_lon,
            centroid_lat=alert_data.centroid_lat,
            recommended_actions=alert_data.recommended_actions or [],
            action_status=(
                alert_data.action_status.value
                if hasattr(alert_data.action_status, "value")
                else str(alert_data.action_status or "pending")
            ),
            action_assigned_to=alert_data.action_assigned_to,
            action_notes=alert_data.action_notes,
            action_due_at=alert_data.action_due_at,
            action_completed_at=alert_data.action_completed_at,
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
        message = self._notification_message(alert)
        
        # Email notification
        try:
            alert_kind = (
                "Condition Alert"
                if "gate condition" in (alert.zone_name or "").lower()
                else "Risk Alert"
            )
            email_sent = await notification_service.send_email_alert(
                subject=f"[MangoPoint] {alert.severity.value.upper()} {alert_kind}",
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

    @staticmethod
    def _notification_message(alert: Alert) -> str:
        """Build notification body with recommended response steps."""
        message = alert.message or "High risk alert detected"
        actions = alert.recommended_actions or []
        if not actions:
            return message

        action_lines = "\n".join(
            f"{idx}. {action}"
            for idx, action in enumerate(actions, start=1)
        )
        return f"{message}\n\nRecommended actions:\n{action_lines}"
    
    async def get_alerts(
        self,
        db: AsyncSession,
        status: Optional[AlertStatus] = None,
        orchard_id: Optional[str] = None,
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
        total_query = select(Alert)
        active_query = select(Alert).where(Alert.status == AlertStatus.ACTIVE)
        
        if status:
            query = query.where(Alert.status == status)
            total_query = total_query.where(Alert.status == status)
        if orchard_id:
            query = query.where(Alert.orchard_id == orchard_id)
            total_query = total_query.where(Alert.orchard_id == orchard_id)
            active_query = active_query.where(Alert.orchard_id == orchard_id)
        
        query = query.limit(limit).offset(offset)
        
        result = await db.execute(query)
        alerts = result.scalars().all()
        
        # Get counts
        total_result = await db.execute(total_query)
        total_count = len(total_result.scalars().all())
        
        active_result = await db.execute(active_query)
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
            if not alert.action_assigned_to:
                alert.action_assigned_to = acknowledged_by
            if alert.action_status == AlertActionStatusEnum.PENDING.value:
                alert.action_status = AlertActionStatusEnum.ASSIGNED.value
            if notes:
                alert.resolution_notes = notes
                alert.action_notes = notes
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
            if alert.action_status not in {
                AlertActionStatusEnum.COMPLETED.value,
                AlertActionStatusEnum.DISMISSED.value,
            }:
                alert.action_status = AlertActionStatusEnum.COMPLETED.value
            if not alert.action_completed_at:
                alert.action_completed_at = alert.resolved_at
            if resolution_notes:
                alert.resolution_notes = resolution_notes
                alert.action_notes = resolution_notes
            await db.flush()
            logger.info(f"Alert {alert_id} resolved")
        
        return alert

    async def update_alert_action(
        self,
        db: AsyncSession,
        alert_id: str,
        action_status: Optional[AlertActionStatusEnum] = None,
        assigned_to: Optional[str] = None,
        notes: Optional[str] = None,
        due_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
    ) -> Optional[Alert]:
        """Update assignment and response workflow fields for an alert."""
        result = await db.execute(
            select(Alert).where(Alert.alert_id == alert_id)
        )
        alert = result.scalar_one_or_none()

        if not alert:
            return None

        if action_status is not None:
            alert.action_status = (
                action_status.value
                if hasattr(action_status, "value")
                else str(action_status)
            )
            if alert.action_status == AlertActionStatusEnum.COMPLETED.value:
                alert.action_completed_at = completed_at or utcnow_naive()
        elif completed_at is not None:
            alert.action_status = AlertActionStatusEnum.COMPLETED.value
            alert.action_completed_at = completed_at

        if assigned_to is not None:
            alert.action_assigned_to = assigned_to
        if notes is not None:
            alert.action_notes = notes
        if due_at is not None:
            alert.action_due_at = due_at

        await db.flush()
        logger.info("Alert %s action workflow updated", alert_id)
        return alert


# Singleton instance
alert_service = AlertService()
