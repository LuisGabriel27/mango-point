"""
MangoPoint API — Monitoring Routes
=====================================
GET /monitoring/metrics — Aggregate monitoring dashboard metrics.
"""

import logging
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
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
