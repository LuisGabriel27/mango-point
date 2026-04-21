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
    AlertStatusEnum,
    AlertSeverityEnum,
)
from db.models import AlertStatus
from ..services.alert_service import alert_service
from utils.datetime_utils import format_rfc3339, utcnow_naive

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["Alerts"])


@router.get(
    "",
    response_model=AlertListResponse,
    summary="List alerts",
    description="""
    Retrieve pest risk alerts.
    
    **Alert triggers:**
    - Risk > 0.75 in any unbagged zone
    
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
            limit=limit,
            offset=offset,
        )
        
        # Convert to response format
        severity_map = {
            "low": AlertSeverityEnum.LOW,
            "medium": AlertSeverityEnum.MEDIUM,
            "high": AlertSeverityEnum.HIGH,
            "critical": AlertSeverityEnum.CRITICAL,
        }
        
        status_map_reverse = {
            AlertStatus.ACTIVE: AlertStatusEnum.ACTIVE,
            AlertStatus.ACKNOWLEDGED: AlertStatusEnum.ACKNOWLEDGED,
            AlertStatus.RESOLVED: AlertStatusEnum.RESOLVED,
        }
        
        alert_responses = []
        for a in alerts:
            alert_responses.append(AlertResponse(
                alert_id=a.alert_id,
                triggered_at=format_rfc3339(a.triggered_at) if a.triggered_at else "",
                severity=severity_map.get(a.severity.value, AlertSeverityEnum.HIGH) if a.severity else AlertSeverityEnum.HIGH,
                status=status_map_reverse.get(a.status, AlertStatusEnum.ACTIVE) if a.status else AlertStatusEnum.ACTIVE,
                risk_value=a.risk_value or 0.0,
                affected_cells=a.affected_cells or [],
                affected_tree_ids=a.affected_tree_ids or [],
                orchard_id=a.orchard_id,
                zone_name=a.zone_name,
                message=a.message or "",
                email_sent=a.email_sent or False,
                sms_sent=a.sms_sent or False,
                acknowledged_by=a.acknowledged_by,
                acknowledged_at=format_rfc3339(a.acknowledged_at) if a.acknowledged_at else None,
                resolved_at=format_rfc3339(a.resolved_at) if a.resolved_at else None,
            ))
        
        return AlertListResponse(
            total=total,
            active_count=active_count,
            alerts=alert_responses,
        )
        
    except Exception as e:
        logger.warning(f"Could not retrieve alerts from database: {e}")
        # Fall back to in-memory alerts when database is not available
        memory_alerts, total, active_count = alert_service.get_memory_alerts(
            status=status.value if status else None
        )
        
        alert_responses = []
        for a in memory_alerts:
            alert_responses.append(AlertResponse(
                alert_id=a["alert_id"],
                triggered_at=a["triggered_at"],
                severity=AlertSeverityEnum(a["severity"]) if a["severity"] in ["low", "medium", "high", "critical"] else AlertSeverityEnum.HIGH,
                status=AlertStatusEnum(a["status"]) if a["status"] in ["active", "acknowledged", "resolved"] else AlertStatusEnum.ACTIVE,
                risk_value=a["risk_value"] or 0.0,
                affected_cells=a["affected_cells"] or [],
                affected_tree_ids=a["affected_tree_ids"] or [],
                orchard_id=a["orchard_id"],
                zone_name=a["zone_name"],
                message=a["message"] or "",
                email_sent=a["email_sent"] or False,
                sms_sent=a["sms_sent"] or False,
                acknowledged_by=a["acknowledged_by"],
                acknowledged_at=a["acknowledged_at"],
                resolved_at=a["resolved_at"],
            ))
        
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
        raise HTTPException(status_code=404, detail="Alert not found")
    
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
        acknowledged_by=alert.acknowledged_by,
        acknowledged_at=format_rfc3339(alert.acknowledged_at) if alert.acknowledged_at else None,
        resolved_at=format_rfc3339(alert.resolved_at) if alert.resolved_at else None,
    )


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
