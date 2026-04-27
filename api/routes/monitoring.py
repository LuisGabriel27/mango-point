"""
MangoPoint API — Monitoring Routes
=====================================
GET /monitoring/metrics — Aggregate monitoring dashboard metrics.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.database import get_db
from ..services.alert_monitoring_service import alert_monitoring_service
from ..services.monitoring_service import monitoring_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/monitoring", tags=["Monitoring"])


@router.get(
    "/metrics",
    summary="Get monitoring dashboard metrics",
    description="""
    Returns all monitoring metrics in a single aggregated response.
    
    **Metrics included:**
    - **infestation_rate**: Percentage of trees currently infested
    - **pest_trend**: Time-series of infestation counts by pest species and day
    - **risk_index**: Composite pest risk score (0–100) with level classification
    - **phenology**: Distribution of trees across growth stages
    - **infestation_spread**: Cumulative + daily new infestations over time
    - **environment**: Current and recent environmental conditions
    - **alert_summary**: Alert counts by severity, recent active alerts
    - **hotspots**: Tree locations with infestation levels for heatmap
    
    Each sub-metric is computed independently; if one fails, others
    still return their data with sensible defaults.
    """,
)
async def get_monitoring_metrics(
    db: AsyncSession = Depends(get_db),
):
    """Compute and return all monitoring metrics."""
    try:
        metrics = await monitoring_service.get_all_metrics(db)
        return metrics
    except Exception as e:
        logger.error(f"[Monitoring] Failed to compute metrics: {e}")
        # Return empty structure so dashboard doesn't break
        return {
            "infestation_rate": {"rate": 0, "infested_trees": 0, "total_trees": 0},
            "pest_trend": [],
            "risk_index": {"score": 0, "level": "low", "factors": {}},
            "phenology": [],
            "infestation_spread": [],
            "environment": {"current": {}, "trends": []},
            "alert_summary": {"total": 0, "active": 0, "by_severity": {}, "recent": []},
            "hotspots": [],
            "computed_at": None,
            "error": str(e),
        }


@router.get(
    "/alerts/status",
    summary="Get scheduled alert monitoring status",
    description="Return scheduler configuration and the latest orchard alert scan summary.",
)
async def get_alert_monitoring_status():
    """Return scheduled alert monitoring status."""
    return alert_monitoring_service.status()


@router.post(
    "/alerts/scan",
    summary="Run orchard alert scan",
    description="""
    Manually scan monitored orchards for biological gate alerts.

    This uses each orchard's configured phenological stage, monitored pest
    list, and centroid/GeoJSON location to fetch forecast weather and create
    condition alerts when pest gates open.
    """,
)
async def run_alert_monitoring_scan(
    orchard_id: Optional[str] = Query(None, description="Optional orchard ID to scan."),
    hours: int = Query(
        settings.ALERT_MONITORING_FORECAST_HOURS,
        ge=1,
        le=168,
        description="Forecast hours to evaluate.",
    ),
    send_notifications: bool = Query(
        True,
        description="Send configured email/SMS notifications for created alerts.",
    ),
    dedupe_hours: int = Query(
        settings.ALERT_MONITORING_DEDUPE_HOURS,
        ge=0,
        le=168,
        description="Suppress duplicate active alerts for this many hours.",
    ),
    db: AsyncSession = Depends(get_db),
):
    """Run an immediate orchard-aware alert scan."""
    return await alert_monitoring_service.scan_orchards(
        db=db,
        orchard_id=orchard_id,
        hours=hours,
        send_notifications=send_notifications,
        dedupe_hours=dedupe_hours,
    )
