"""
MangoPoint API — Alert Routes
===============================
GET /alerts endpoint for risk alerts.
"""

import logging
from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.security import get_current_active_user
from ..models.schemas import (
    AlertResponse,
    AlertListResponse,
    AlertAcknowledge,
    AlertActionStatusEnum,
    AlertActionUpdate,
    AlertEmailRecipientCreate,
    AlertEmailRecipientResponse,
    AlertEmailRecipientUpdate,
    AlertStatusEnum,
    AlertSeverityEnum,
    WeatherForecastCheckRequest,
)
from ..core.config import settings
from db.models import AlertStatus, UserAccount, UserRoleEnum
from ..services.alert_recipient_service import (
    AlertRecipientEmailConflictError,
    alert_recipient_service,
)
from ..services.alert_service import alert_service
from ..services.notification_service import notification_service
from ..services.weather_service import weather_service
from utils.datetime_utils import format_rfc3339, utcnow_naive

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["Alerts"])


def _require_admin(current_user: UserAccount) -> None:
    role = (
        current_user.role
        if isinstance(current_user.role, UserRoleEnum)
        else UserRoleEnum(str(current_user.role))
    )
    if role != UserRoleEnum.ADMIN:
        raise HTTPException(status_code=403, detail="Administrator access is required.")


def _memory_alert_to_response(alert: dict) -> AlertResponse:
    """Convert an in-memory fallback alert to API response shape."""
    return AlertResponse(
        alert_id=alert["alert_id"],
        simulation_run_id=alert.get("simulation_run_id"),
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
        suggested_simulation_params=alert.get("suggested_simulation_params"),
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
        simulation_run_id=alert.simulation_run_id,
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
        suggested_simulation_params=getattr(alert, "suggested_simulation_params", None),
    )


def _alert_response_payload(alert: AlertResponse) -> dict[str, Any]:
    """Convert an API alert response to the service fingerprint shape."""
    return {
        "alert_id": alert.alert_id,
        "status": alert.status.value if hasattr(alert.status, "value") else str(alert.status),
        "orchard_id": alert.orchard_id,
        "zone_name": alert.zone_name,
        "message": alert.message,
        "affected_cells": alert.affected_cells,
        "affected_tree_ids": alert.affected_tree_ids,
    }


def _dedupe_alert_responses(alerts: List[AlertResponse]) -> List[AlertResponse]:
    """Collapse duplicate active alerts across database and memory sources."""
    unique: List[AlertResponse] = []
    seen_active = set()

    for alert in alerts:
        status = alert.status.value if hasattr(alert.status, "value") else str(alert.status)
        if status == AlertStatusEnum.ACTIVE.value:
            fingerprint = alert_service.alert_fingerprint(_alert_response_payload(alert))
            if fingerprint in seen_active:
                continue
            seen_active.add(fingerprint)
        unique.append(alert)

    return unique


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
        pre_dedupe_count = len(alert_responses)
        pre_dedupe_active = len([
            alert for alert in alert_responses
            if alert.status == AlertStatusEnum.ACTIVE
        ])
        alert_responses = _dedupe_alert_responses(alert_responses)
        post_dedupe_active = len([
            alert for alert in alert_responses
            if alert.status == AlertStatusEnum.ACTIVE
        ])
        total = max(len(alert_responses), total - (pre_dedupe_count - len(alert_responses)))
        active_count = max(post_dedupe_active, active_count - (pre_dedupe_active - post_dedupe_active))
        
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
        alert_responses = _dedupe_alert_responses(alert_responses)
        total = len(alert_responses)
        active_count = len([
            alert for alert in alert_responses
            if alert.status == AlertStatusEnum.ACTIVE
        ])
        
        return AlertListResponse(
            total=total,
            active_count=active_count,
            alerts=alert_responses,
        )


@router.delete(
    "/clear",
    summary="Clear all alerts",
    description="Clear all in-memory alerts. Used when refreshing the dashboard.",
)
async def clear_alerts():
    """Clear all in-memory alerts so the dashboard starts fresh."""
    alert_service.clear_memory_alerts()
    logger.info("All in-memory alerts cleared via /alerts/clear")
    return {"status": "ok", "message": "All alerts cleared"}


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


@router.post(
    "/check-weather-forecast",
    response_model=AlertListResponse,
    summary="Check weather forecast for pest alerts",
    description="""
    Fetch the 48-hour weather forecast and create pre-emptive pest risk alerts when
    rain is expected.

    **Why this matters:**
    Rain is the primary environmental trigger for both Cecid Fly (fruitlet stage) and
    Fruit Fly (mature stage).  Each generated alert includes a `suggested_simulation_params`
    payload so growers can immediately run an informed simulation without guessing at
    parameters.

    **Deduplication:** repeated calls for the same orchard + pest combination do not
    create duplicate active alerts.
    """,
)
async def check_weather_forecast(
    body: WeatherForecastCheckRequest,
    db: AsyncSession = Depends(get_db),
) -> AlertListResponse:
    """Fetch forecast, create weather-triggered alerts with suggested sim params."""
    lat = body.lat if body.lat is not None else settings.DEFAULT_LAT
    lon = body.lon if body.lon is not None else settings.DEFAULT_LON

    try:
        weather_bundle = await weather_service.get_forecast_bundle(
            lat=lat, lon=lon, hours=48,
        )
        forecast = weather_bundle["forecast"]
        antecedent = weather_bundle.get("antecedent", [])
        provenance = weather_bundle.get("provenance", {})
    except Exception as exc:
        logger.warning("Weather forecast unavailable for alert check: %s", exc)
        forecast = []
        antecedent = []
        provenance = {"provider": "unavailable", "fallback_reason": str(exc)}

    alert_data_list = alert_service.check_weather_forecast_alerts(
        forecast=forecast,
        orchard_id=body.orchard_id,
        lat=lat,
        lon=lon,
        orchard_stage=body.orchard_stage,
        monitored_pest_types=body.monitored_pest_types,
        antecedent=antecedent,
        provenance=provenance,
    )

    created_responses: list[AlertResponse] = []
    for alert_data in alert_data_list:
        try:
            alert = await alert_service.create_alert(db, alert_data, send_notifications=True)
            await db.flush()
            created_responses.append(_db_alert_to_response(alert))
        except Exception as exc:
            logger.warning("DB unavailable for weather alert, using memory: %s", exc)
            newly_stored = alert_service.store_alert_in_memory(alert_data)
            email_sent = False
            sms_sent = False
            if newly_stored:
                email_sent, sms_sent = await alert_service.send_notifications_for_alert_data(
                    alert_data,
                )
                alert_service.update_memory_alert(
                    alert_data.alert_id,
                    email_sent=email_sent,
                    email_sent_at=(
                        format_rfc3339(utcnow_naive()) if email_sent else None
                    ),
                    sms_sent=sms_sent,
                )
            created_responses.append(_memory_alert_to_response({
                **alert_data.model_dump(),
                "triggered_at": format_rfc3339(utcnow_naive()),
                "status": "active",
                "email_sent": email_sent,
                "sms_sent": sms_sent,
                "acknowledged_by": None,
                "acknowledged_at": None,
                "resolved_at": None,
            }))

    try:
        await db.commit()
    except Exception:
        pass

    return AlertListResponse(
        total=len(created_responses),
        active_count=len(created_responses),
        alerts=created_responses,
    )


@router.get(
    "/email/status",
    summary="Get alert email configuration status",
    description="Return non-secret provider and designated-recipient diagnostics.",
)
async def get_alert_email_status(
    db: AsyncSession = Depends(get_db),
):
    """Expose only masked email delivery diagnostics."""
    recipients = await alert_recipient_service.effective_emails(db)
    return notification_service.email_status(recipients)


@router.get(
    "/email/recipients",
    response_model=list[AlertEmailRecipientResponse],
    summary="List designated alert email recipients",
    description="List active and paused recipients assigned by an administrator.",
)
async def list_alert_email_recipients(
    current_user: UserAccount = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the admin-managed recipient list, importing `.env` defaults once."""
    _require_admin(current_user)
    recipients = await alert_recipient_service.list_all(
        db,
        bootstrap_environment=True,
    )
    await db.commit()
    return recipients


@router.post(
    "/email/recipients",
    response_model=AlertEmailRecipientResponse,
    status_code=201,
    summary="Add an alert email recipient",
    description="Assign a farmer or other significant person to receive alert emails.",
)
async def add_alert_email_recipient(
    body: AlertEmailRecipientCreate,
    current_user: UserAccount = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Create or reactivate one designated recipient."""
    _require_admin(current_user)
    recipient = await alert_recipient_service.add_or_reactivate(
        db,
        email=body.email,
        name=body.name,
        created_by_user_id=current_user.user_id,
    )
    await db.commit()
    return recipient


@router.patch(
    "/email/recipients/{recipient_id}",
    response_model=AlertEmailRecipientResponse,
    summary="Update an alert email recipient",
    description="Edit recipient details or pause/resume future alert emails.",
)
async def update_alert_email_recipient(
    recipient_id: int,
    body: AlertEmailRecipientUpdate,
    current_user: UserAccount = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Update one designated recipient without changing alert delivery logic."""
    _require_admin(current_user)
    try:
        recipient = await alert_recipient_service.update(
            db,
            recipient_id,
            email=body.email,
            name=body.name,
            update_name="name" in body.model_fields_set,
            is_active=body.is_active,
        )
    except AlertRecipientEmailConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if recipient is None:
        raise HTTPException(status_code=404, detail="Alert email recipient not found.")
    await db.commit()
    return recipient


@router.delete(
    "/email/recipients/{recipient_id}",
    response_model=AlertEmailRecipientResponse,
    summary="Permanently delete an alert email recipient",
    description="Permanently remove a designated recipient and their contact details.",
)
async def remove_alert_email_recipient(
    recipient_id: int,
    current_user: UserAccount = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Hard-delete a recipient while preserving intentional empty-list state."""
    _require_admin(current_user)
    recipient = await alert_recipient_service.hard_delete(db, recipient_id)
    if recipient is None:
        raise HTTPException(status_code=404, detail="Alert email recipient not found.")
    await db.commit()
    return recipient


@router.post(
    "/email/test",
    summary="Send a test alert email",
    description="Send one test message to all configured designated farmers (admin only).",
)
async def send_test_alert_email(
    current_user: UserAccount = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Let an administrator verify provider and inbox delivery end to end."""
    _require_admin(current_user)

    recipients = await alert_recipient_service.effective_emails(db)
    status_payload = notification_service.email_status(recipients)
    if not status_payload["configured"]:
        detail = status_payload.get("configuration_error") or status_payload.get("last_error") or (
            "Email notifications are not fully configured. Check server environment settings."
        )
        raise HTTPException(status_code=503, detail=detail)

    sent = await notification_service.send_email_alert(
        subject="[MangoPoint] Test farmer notification",
        message=(
            "This is a test of MangoPoint's off-site pest alert email channel. "
            "If you received it, the designated farmer notification setup is working."
        ),
        alert_id=f"email-test-{int(utcnow_naive().timestamp())}",
        recipients=recipients,
    )
    if not sent:
        raise HTTPException(
            status_code=502,
            detail=notification_service.last_error or "The email provider rejected the test email.",
        )

    return {
        "sent": True,
        "recipient_count": len(recipients),
        "provider": notification_service.email_provider,
        "message": "Test email accepted by the configured provider.",
    }


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
