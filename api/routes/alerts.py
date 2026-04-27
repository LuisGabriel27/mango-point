"""
MangoPoint API — Alert Routes
===============================
GET /alerts endpoint for risk alerts.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..models.schemas import (
    AlertResponse,
    AlertListResponse,
    AlertAcknowledge,
    AlertActionStatusEnum,
    AlertActionUpdate,
    AlertStatusEnum,
    AlertSeverityEnum,
)
from db.models import AlertStatus
from ..services.alert_service import alert_service
from utils.datetime_utils import format_rfc3339, utcnow_naive

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["Alerts"])


def _memory_alert_to_response(alert: dict) -> AlertResponse:
    """Convert an in-memory fallback alert to API response shape."""
    return AlertResponse(
        alert_id=alert["alert_id"],
        triggered_at=alert["triggered_at"],
        severity=(
            AlertSeverityEnum(alert["severity"])
            if alert["severity"] in ["low", "medium", "high", "critical"]
            else AlertSeverityEnum.HIGH
        ),
        status=(
            AlertStatusEnum(alert["status"])
            if alert["status"] in ["active", "acknowledged", "resolved"]
            else AlertStatusEnum.ACTIVE
        ),
        risk_value=alert["risk_value"] or 0.0,
        affected_cells=alert["affected_cells"] or [],
        affected_tree_ids=alert["affected_tree_ids"] or [],
        orchard_id=alert["orchard_id"],
        zone_name=alert["zone_name"],
        message=alert["message"] or "",
        email_sent=alert["email_sent"] or False,
        sms_sent=alert["sms_sent"] or False,
        centroid_lon=alert.get("centroid_lon"),
        centroid_lat=alert.get("centroid_lat"),
        acknowledged_by=alert["acknowledged_by"],
        acknowledged_at=alert["acknowledged_at"],
        resolved_at=alert["resolved_at"],
        recommended_actions=alert.get("recommended_actions") or [],
        action_status=(
            AlertActionStatusEnum(alert.get("action_status", "pending"))
            if alert.get("action_status", "pending") in [
                "pending", "assigned", "in_progress", "completed", "dismissed"
            ]
            else AlertActionStatusEnum.PENDING
        ),
        action_assigned_to=alert.get("action_assigned_to"),
        action_notes=alert.get("action_notes"),
        action_due_at=alert.get("action_due_at"),
        action_completed_at=alert.get("action_completed_at"),
    )


def _db_alert_to_response(alert) -> AlertResponse:
    """Convert a database alert row to API response shape."""
    severity_map = {
        "low": AlertSeverityEnum.LOW,
        "medium": AlertSeverityEnum.MEDIUM,
        "high": AlertSeverityEnum.HIGH,
        "critical": AlertSeverityEnum.CRITICAL,
    }

    status_map = {
        AlertStatus.ACTIVE: AlertStatusEnum.ACTIVE,
        AlertStatus.ACKNOWLEDGED: AlertStatusEnum.ACKNOWLEDGED,
        AlertStatus.RESOLVED: AlertStatusEnum.RESOLVED,
    }

    action_status_value = alert.action_status or "pending"
    try:
        action_status = AlertActionStatusEnum(action_status_value)
    except ValueError:
        action_status = AlertActionStatusEnum.PENDING

    return AlertResponse(
        alert_id=alert.alert_id,
        triggered_at=format_rfc3339(alert.triggered_at) if alert.triggered_at else "",
        severity=severity_map.get(alert.severity.value, AlertSeverityEnum.HIGH) if alert.severity else AlertSeverityEnum.HIGH,
        status=status_map.get(alert.status, AlertStatusEnum.ACTIVE) if alert.status else AlertStatusEnum.ACTIVE,
        risk_value=alert.risk_value or 0.0,
        affected_cells=alert.affected_cells or [],
        affected_tree_ids=alert.affected_tree_ids or [],
        orchard_id=alert.orchard_id,
        zone_name=alert.zone_name,
        message=alert.message or "",
        email_sent=alert.email_sent or False,
        sms_sent=alert.sms_sent or False,
        centroid_lon=alert.centroid_lon,
        centroid_lat=alert.centroid_lat,
        acknowledged_by=alert.acknowledged_by,
        acknowledged_at=format_rfc3339(alert.acknowledged_at) if alert.acknowledged_at else None,
        resolved_at=format_rfc3339(alert.resolved_at) if alert.resolved_at else None,
        recommended_actions=alert.recommended_actions or [],
        action_status=action_status,
        action_assigned_to=alert.action_assigned_to,
        action_notes=alert.action_notes,
        action_due_at=format_rfc3339(alert.action_due_at) if alert.action_due_at else None,
        action_completed_at=format_rfc3339(alert.action_completed_at) if alert.action_completed_at else None,
    )


@router.get(
    "",
    response_model=AlertListResponse,
    summary="List alerts",
    description="""
    Retrieve pest risk alerts.
    
    **Alert triggers:**
    - Risk > 0.75 in any unbagged zone
    - Pest biological gate opens under forecast weather and orchard stage
    
    **Severity levels:**
    - **Critical**: Risk ≥ 95% or > 50 affected cells
    - **High**: Risk ≥ 85% or > 20 affected cells
    - **Medium**: Risk ≥ 75% or > 10 affected cells
    - **Low**: Below thresholds
    
    **Status:**
    - **Active**: Requires attention
    - **Acknowledged**: Under review
    - **Resolved**: Issue addressed
    """,
)
async def get_alerts(
    status: Optional[AlertStatusEnum] = Query(
        None,
        description="Filter by alert status",
    ),
    orchard_id: Optional[str] = Query(
        None,
        description="Filter by orchard ID",
    ),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> AlertListResponse:
    """
    Get list of alerts with optional status filter.
    """
    try:
        # Map enum
        status_map = {
            AlertStatusEnum.ACTIVE: AlertStatus.ACTIVE,
            AlertStatusEnum.ACKNOWLEDGED: AlertStatus.ACKNOWLEDGED,
            AlertStatusEnum.RESOLVED: AlertStatus.RESOLVED,
        }
        
        db_status = status_map.get(status) if status else None
        
        alerts, total, active_count = await alert_service.get_alerts(
            db=db,
            status=db_status,
            orchard_id=orchard_id,
            limit=limit,
            offset=offset,
        )
        
        alert_responses = [_db_alert_to_response(a) for a in alerts]

        seen_alert_ids = {alert.alert_id for alert in alert_responses}
        status_filter = status.value if status else None
        memory_alerts, _, _ = alert_service.get_memory_alerts(
            status=status_filter,
            orchard_id=orchard_id,
        )
        all_memory_alerts, _, _ = alert_service.get_memory_alerts(
            orchard_id=orchard_id,
        )
        unique_memory_alerts = [
            alert for alert in memory_alerts
            if alert["alert_id"] not in seen_alert_ids
        ]
        alert_responses.extend(
            _memory_alert_to_response(alert)
            for alert in unique_memory_alerts
        )
        total += len(unique_memory_alerts)
        active_count += len([
            alert for alert in all_memory_alerts
            if alert["status"] == "active" and alert["alert_id"] not in seen_alert_ids
        ])
        
        return AlertListResponse(
            total=total,
            active_count=active_count,
            alerts=alert_responses,
        )
        
    except Exception as e:
        logger.warning(f"Could not retrieve alerts from database: {e}")
        # Fall back to in-memory alerts when database is not available
        memory_alerts, total, active_count = alert_service.get_memory_alerts(
            status=status.value if status else None,
            orchard_id=orchard_id,
        )
        
        alert_responses = []
        for a in memory_alerts:
            alert_responses.append(_memory_alert_to_response(a))
        
        return AlertListResponse(
            total=total,
            active_count=active_count,
            alerts=alert_responses,
        )


@router.get(
    "/{alert_id}",
    response_model=AlertResponse,
    summary="Get alert details",
    description="Get details of a specific alert.",
)
async def get_alert(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
) -> AlertResponse:
    """Get a specific alert by ID."""
    from sqlalchemy import select
    from db.models import Alert
    
    result = await db.execute(
        select(Alert).where(Alert.alert_id == alert_id)
    )
    alert = result.scalar_one_or_none()
    
    if not alert:
        memory_alerts, _, _ = alert_service.get_memory_alerts()
        for memory_alert in memory_alerts:
            if memory_alert["alert_id"] == alert_id:
                return _memory_alert_to_response(memory_alert)
        raise HTTPException(status_code=404, detail="Alert not found")
    
    return _db_alert_to_response(alert)


@router.post(
    "/{alert_id}/acknowledge",
    response_model=AlertResponse,
    summary="Acknowledge alert",
    description="Mark an alert as acknowledged.",
)
async def acknowledge_alert(
    alert_id: str,
    ack: AlertAcknowledge,
    db: AsyncSession = Depends(get_db),
) -> AlertResponse:
    """Acknowledge an alert."""
    try:
        alert = await alert_service.acknowledge_alert(
            db=db,
            alert_id=alert_id,
            acknowledged_by=ack.acknowledged_by,
            notes=ack.notes,
        )
        
        if not alert:
            memory_alert = alert_service.update_memory_alert(
                alert_id,
                status="acknowledged",
                acknowledged_by=ack.acknowledged_by,
                acknowledged_at=format_rfc3339(utcnow_naive()),
                action_assigned_to=ack.acknowledged_by,
                action_status="assigned",
                action_notes=ack.notes,
            )
            if memory_alert:
                return _memory_alert_to_response(memory_alert)
            raise HTTPException(status_code=404, detail="Alert not found")
        
        await db.commit()
        
        # Return updated alert
        return await get_alert(alert_id, db)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to acknowledge alert: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to acknowledge alert: {str(e)}",
        )


@router.post(
    "/{alert_id}/resolve",
    response_model=AlertResponse,
    summary="Resolve alert",
    description="Mark an alert as resolved.",
)
async def resolve_alert(
    alert_id: str,
    resolution_notes: Optional[str] = Query(None, description="Resolution notes"),
    db: AsyncSession = Depends(get_db),
) -> AlertResponse:
    """Resolve an alert."""
    try:
        alert = await alert_service.resolve_alert(
            db=db,
            alert_id=alert_id,
            resolution_notes=resolution_notes,
        )
        
        if not alert:
            now = format_rfc3339(utcnow_naive())
            memory_alert = alert_service.update_memory_alert(
                alert_id,
                status="resolved",
                resolved_at=now,
                action_status="completed",
                action_completed_at=now,
                action_notes=resolution_notes,
            )
            if memory_alert:
                return _memory_alert_to_response(memory_alert)
            raise HTTPException(status_code=404, detail="Alert not found")
        
        await db.commit()
        
        # Return updated alert
        return await get_alert(alert_id, db)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resolve alert: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to resolve alert: {str(e)}",
        )


@router.post(
    "/{alert_id}/action",
    response_model=AlertResponse,
    summary="Update alert action workflow",
    description="Assign or update the field response work for an alert.",
)
async def update_alert_action(
    alert_id: str,
    action: AlertActionUpdate,
    db: AsyncSession = Depends(get_db),
) -> AlertResponse:
    """Update alert action assignment/status/notes."""
    try:
        alert = await alert_service.update_alert_action(
            db=db,
            alert_id=alert_id,
            action_status=action.action_status,
            assigned_to=action.assigned_to,
            notes=action.notes,
            due_at=action.due_at,
            completed_at=action.completed_at,
        )

        if not alert:
            completed_at = action.completed_at or (
                utcnow_naive()
                if action.action_status == AlertActionStatusEnum.COMPLETED
                else None
            )
            memory_alert = alert_service.update_memory_alert(
                alert_id,
                action_status=(
                    action.action_status.value
                    if action.action_status
                    else None
                ),
                action_assigned_to=action.assigned_to,
                action_notes=action.notes,
                action_due_at=(
                    format_rfc3339(action.due_at)
                    if action.due_at
                    else None
                ),
                action_completed_at=(
                    format_rfc3339(completed_at)
                    if completed_at
                    else None
                ),
            )
            if memory_alert:
                return _memory_alert_to_response(memory_alert)
            raise HTTPException(status_code=404, detail="Alert not found")

        await db.commit()
        return await get_alert(alert_id, db)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update alert action: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update alert action: {str(e)}",
        )


@router.get(
    "/stats/summary",
    summary="Alert statistics",
    description="Get summary statistics for alerts.",
)
async def get_alert_stats(
    db: AsyncSession = Depends(get_db),
):
    """Get alert statistics."""
    from sqlalchemy import select, func
    from db.models import Alert
    
    # Total counts by status
    result = await db.execute(
        select(Alert.status, func.count(Alert.id))
        .group_by(Alert.status)
    )
    status_counts = {str(row[0].value) if row[0] else "unknown": row[1] for row in result}
    
    # Counts by severity
    result = await db.execute(
        select(Alert.severity, func.count(Alert.id))
        .group_by(Alert.severity)
    )
    severity_counts = {str(row[0].value) if row[0] else "unknown": row[1] for row in result}
    
    # Recent alerts (last 24 hours)
    recent_count = await db.execute(
        select(func.count(Alert.id))
        .where(Alert.triggered_at >= utcnow_naive().replace(hour=0, minute=0, second=0))
    )
    today_count = recent_count.scalar() or 0
    
    return {
        "by_status": status_counts,
        "by_severity": severity_counts,
        "today_count": today_count,
        "total": sum(status_counts.values()),
    }
