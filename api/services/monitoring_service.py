"""
MangoPoint API — Monitoring Service
======================================
Computes monitoring dashboard metrics from PostgreSQL database.

Provides aggregated metrics for:
- Active infestation rate
- Pest population trends
- Pest risk index
- Phenology distribution
- Infestation spread over time
- Environmental trends
- Alert summary
- Infestation hotspots
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

from sqlalchemy import select, func, case, desc, and_, text, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class MonitoringService:
    """Service for computing monitoring dashboard metrics."""

    async def get_all_metrics(self, db: AsyncSession) -> Dict[str, Any]:
        """
        Compute all monitoring metrics in a single call.
        Returns a dict ready for JSON serialisation.
        """
        results = {}

        try:
            results["infestation_rate"] = await self._get_infestation_rate(db)
        except Exception as e:
            logger.warning(f"[Monitoring] infestation_rate failed: {e}")
            results["infestation_rate"] = {"rate": 0, "infested_trees": 0, "total_trees": 0}

        try:
            results["pest_trend"] = await self._get_pest_population_trend(db)
        except Exception as e:
            logger.warning(f"[Monitoring] pest_trend failed: {e}")
            results["pest_trend"] = []

        try:
            results["risk_index"] = await self._get_pest_risk_index(db)
        except Exception as e:
            logger.warning(f"[Monitoring] risk_index failed: {e}")
            results["risk_index"] = {"score": 0, "level": "low", "factors": {}}

        try:
            results["phenology"] = await self._get_phenology_distribution(db)
        except Exception as e:
            logger.warning(f"[Monitoring] phenology failed: {e}")
            results["phenology"] = []

        try:
            results["infestation_spread"] = await self._get_infestation_spread(db)
        except Exception as e:
            logger.warning(f"[Monitoring] infestation_spread failed: {e}")
            results["infestation_spread"] = []

        try:
            results["environment"] = await self._get_environmental_trends(db)
        except Exception as e:
            logger.warning(f"[Monitoring] environment failed: {e}")
            results["environment"] = {"current": {}, "trends": []}

        try:
            results["alert_summary"] = await self._get_alert_summary(db)
        except Exception as e:
            logger.warning(f"[Monitoring] alert_summary failed: {e}")
            results["alert_summary"] = {"total": 0, "active": 0, "by_severity": {}, "recent": []}

        try:
            results["hotspots"] = await self._get_infestation_hotspots(db)
        except Exception as e:
            logger.warning(f"[Monitoring] hotspots failed: {e}")
            results["hotspots"] = []

        results["computed_at"] = datetime.utcnow().isoformat() + "Z"
        return results

    # ─────────────────────────────────────────────
    #  1. Active Infestation Rate
    # ─────────────────────────────────────────────
    async def _get_infestation_rate(self, db: AsyncSession) -> Dict[str, Any]:
        """
        Percentage of trees currently infected.
        Uses tree.status = 'infected' as the primary indicator.
        Also counts trees with active infestation_records.
        """
        from db.models import Tree, InfestationRecord, TreeStatusEnum

        # Total trees
        total_result = await db.execute(select(func.count(Tree.tree_id)))
        total_trees = total_result.scalar() or 0

        if total_trees == 0:
            return {"rate": 0, "infested_trees": 0, "total_trees": 0}

        # Trees with status = infected
        infected_result = await db.execute(
            select(func.count(Tree.tree_id))
            .where(Tree.status == TreeStatusEnum.INFECTED)
        )
        infected_count = infected_result.scalar() or 0

        # Also count trees with infestation records (infected_status = true)
        infested_via_records = await db.execute(
            select(func.count(func.distinct(InfestationRecord.tree_id)))
            .where(InfestationRecord.infected_status == True)  # noqa: E712
        )
        records_count = infested_via_records.scalar() or 0

        # Use the higher of the two counts for a comprehensive view
        infested_trees = max(infected_count, records_count)
        rate = infested_trees / total_trees if total_trees > 0 else 0

        return {
            "rate": round(rate, 4),
            "infested_trees": infested_trees,
            "total_trees": total_trees,
        }

    # ─────────────────────────────────────────────
    #  2. Pest Population Trend
    # ─────────────────────────────────────────────
    async def _get_pest_population_trend(self, db: AsyncSession) -> List[Dict[str, Any]]:
        """
        Time-series of infestation counts grouped by day and pest name.
        Returns list of {date, pest_name, count}.
        """
        from db.models import InfestationRecord, Pest

        result = await db.execute(
            select(
                cast(InfestationRecord.record_date, Date).label("date"),
                Pest.name.label("pest_name"),
                func.count(InfestationRecord.infestation_id).label("count"),
            )
            .join(Pest, InfestationRecord.pest_id == Pest.pest_id)
            .where(InfestationRecord.record_date.isnot(None))
            .group_by(
                cast(InfestationRecord.record_date, Date),
                Pest.name,
            )
            .order_by(cast(InfestationRecord.record_date, Date))
        )
        rows = result.all()

        return [
            {
                "date": row.date.isoformat() if row.date else None,
                "pest_name": row.pest_name,
                "count": row.count,
            }
            for row in rows
        ]

    # ─────────────────────────────────────────────
    #  3. Pest Risk Index (0–100)
    # ─────────────────────────────────────────────
    async def _get_pest_risk_index(self, db: AsyncSession) -> Dict[str, Any]:
        """
        Composite risk score based on:
        - Temperature (optimal 25-35°C for tropical pests)
        - Humidity (> 70% increases risk)
        - Rainfall in last 24h (triggers pest emergence)
        - Current pest population level
        - Phenology stage (fruitlet/mature = higher risk)
        
        Returns normalised score 0-100 and risk level label.
        """
        from db.models import (
            EnvironmentalCondition, InfestationRecord, MangoStage,
            SimulationRun, Tree, MangoStageStatusEnum,
        )

        factors: Dict[str, float] = {}

        # --- Temperature score (weight 25%) ---
        temp_result = await db.execute(
            select(EnvironmentalCondition.temperature)
            .order_by(desc(EnvironmentalCondition.condition_id))
            .limit(1)
        )
        temp = temp_result.scalar()
        if temp is not None:
            temp = float(temp)
            # Optimal pest range 25-35°C
            if 25 <= temp <= 35:
                factors["temperature"] = 1.0
            elif 20 <= temp < 25 or 35 < temp <= 40:
                factors["temperature"] = 0.6
            else:
                factors["temperature"] = 0.2
        else:
            factors["temperature"] = 0.0

        # --- Humidity score (weight 25%) ---
        hum_result = await db.execute(
            select(EnvironmentalCondition.humidity)
            .order_by(desc(EnvironmentalCondition.condition_id))
            .limit(1)
        )
        hum = hum_result.scalar()
        if hum is not None:
            hum = float(hum)
            factors["humidity"] = min(hum / 100.0, 1.0) if hum > 50 else hum / 200.0
        else:
            factors["humidity"] = 0.0

        # --- Rainfall score (weight 15%) ---
        rain_result = await db.execute(
            select(func.sum(EnvironmentalCondition.rainfall))
            .where(
                EnvironmentalCondition.condition_date >= datetime.utcnow() - timedelta(hours=24)
            )
        )
        total_rain = rain_result.scalar()
        if total_rain is not None:
            total_rain = float(total_rain)
            # Rainfall > 5mm triggers emergence; > 20mm very high risk
            factors["rainfall"] = min(total_rain / 20.0, 1.0)
        else:
            factors["rainfall"] = 0.0

        # --- Pest population level (weight 20%) ---
        total_trees_result = await db.execute(select(func.count(Tree.tree_id)))
        total_trees = total_trees_result.scalar() or 1
        infested_result = await db.execute(
            select(func.count(func.distinct(InfestationRecord.tree_id)))
            .where(InfestationRecord.infected_status == True)  # noqa: E712
        )
        infested = infested_result.scalar() or 0
        factors["pest_population"] = min(infested / max(total_trees, 1), 1.0)

        # --- Phenology stage score (weight 15%) ---
        stage_result = await db.execute(
            select(MangoStage.stage_status)
            .order_by(desc(MangoStage.stage_id))
            .limit(1)
        )
        stage = stage_result.scalar()
        stage_scores = {
            MangoStageStatusEnum.DORMANT: 0.1,
            MangoStageStatusEnum.FLOWERING: 0.3,
            MangoStageStatusEnum.FRUITLET: 0.8,
            MangoStageStatusEnum.MATURE: 1.0,
        }
        factors["phenology"] = stage_scores.get(stage, 0.3)

        # --- Weighted composite ---
        weights = {
            "temperature": 0.25,
            "humidity": 0.25,
            "rainfall": 0.15,
            "pest_population": 0.20,
            "phenology": 0.15,
        }
        score = sum(factors.get(k, 0) * w for k, w in weights.items()) * 100
        score = round(min(max(score, 0), 100), 1)

        # Classify
        if score >= 75:
            level = "critical"
        elif score >= 50:
            level = "high"
        elif score >= 25:
            level = "moderate"
        else:
            level = "low"

        return {
            "score": score,
            "level": level,
            "factors": {k: round(v, 3) for k, v in factors.items()},
        }

    # ─────────────────────────────────────────────
    #  4. Phenology Distribution
    # ─────────────────────────────────────────────
    async def _get_phenology_distribution(self, db: AsyncSession) -> List[Dict[str, Any]]:
        """
        Count of trees in each growth stage.
        Uses tree.current_stage as primary source.
        """
        from db.models import Tree

        result = await db.execute(
            select(
                Tree.current_stage,
                func.count(Tree.tree_id).label("count"),
            )
            .group_by(Tree.current_stage)
        )
        rows = result.all()

        return [
            {"stage": row.current_stage.value if hasattr(row.current_stage, "value") else str(row.current_stage), "count": row.count}
            for row in rows
        ]

    # ─────────────────────────────────────────────
    #  5. Infestation Spread Over Time
    # ─────────────────────────────────────────────
    async def _get_infestation_spread(self, db: AsyncSession) -> List[Dict[str, Any]]:
        """
        Cumulative + new infestations per day.
        Returns list of {date, new_count, cumulative}.
        """
        from db.models import InfestationRecord

        result = await db.execute(
            select(
                cast(InfestationRecord.record_date, Date).label("date"),
                func.count(InfestationRecord.infestation_id).label("new_count"),
            )
            .where(InfestationRecord.record_date.isnot(None))
            .group_by(cast(InfestationRecord.record_date, Date))
            .order_by(cast(InfestationRecord.record_date, Date))
        )
        rows = result.all()

        spread = []
        cumulative = 0
        for row in rows:
            cumulative += row.new_count
            spread.append({
                "date": row.date.isoformat() if row.date else None,
                "new_count": row.new_count,
                "cumulative": cumulative,
            })

        return spread

    # ─────────────────────────────────────────────
    #  6. Environmental Trends
    # ─────────────────────────────────────────────
    async def _get_environmental_trends(self, db: AsyncSession) -> Dict[str, Any]:
        """
        Current + recent environmental conditions.
        Includes latest values and time-series from environmental_condition
        and weather_cache tables.
        """
        from db.models import EnvironmentalCondition, WeatherCache

        # Latest from environmental_condition
        latest_result = await db.execute(
            select(EnvironmentalCondition)
            .order_by(desc(EnvironmentalCondition.condition_id))
            .limit(1)
        )
        latest = latest_result.scalar_one_or_none()

        current = {}
        if latest:
            current = {
                "temperature": float(latest.temperature) if latest.temperature is not None else None,
                "humidity": float(latest.humidity) if latest.humidity is not None else None,
                "rainfall": float(latest.rainfall) if latest.rainfall is not None else None,
                "wind_speed": float(latest.wind_speed) if latest.wind_speed is not None else None,
                "date": latest.condition_date.isoformat() if latest.condition_date else None,
            }

        # Also try weather_cache for more recent data
        cache_result = await db.execute(
            select(WeatherCache)
            .order_by(desc(WeatherCache.fetched_at))
            .limit(1)
        )
        cache = cache_result.scalar_one_or_none()

        if cache and (not current or not current.get("temperature")):
            current = {
                "temperature": cache.temperature_c,
                "humidity": cache.humidity,
                "rainfall": None,
                "wind_speed": cache.wind_speed_ms,
                "date": cache.fetched_at.isoformat() if cache.fetched_at else None,
            }

        # Trend data from environmental_condition (last 50 records)
        trend_result = await db.execute(
            select(
                EnvironmentalCondition.condition_date,
                EnvironmentalCondition.temperature,
                EnvironmentalCondition.humidity,
                EnvironmentalCondition.rainfall,
                EnvironmentalCondition.wind_speed,
            )
            .order_by(desc(EnvironmentalCondition.condition_id))
            .limit(50)
        )
        trend_rows = trend_result.all()

        trends = [
            {
                "date": row.condition_date.isoformat() if row.condition_date else None,
                "temperature": float(row.temperature) if row.temperature is not None else None,
                "humidity": float(row.humidity) if row.humidity is not None else None,
                "rainfall": float(row.rainfall) if row.rainfall is not None else None,
                "wind_speed": float(row.wind_speed) if row.wind_speed is not None else None,
            }
            for row in reversed(trend_rows)  # chronological order
        ]

        return {"current": current, "trends": trends}

    # ─────────────────────────────────────────────
    #  7. Alert Summary
    # ─────────────────────────────────────────────
    async def _get_alert_summary(self, db: AsyncSession) -> Dict[str, Any]:
        """Aggregate alert counts by severity and status."""
        from db.models import Alert, AlertStatus as AlertStatusModel

        # Total
        total_result = await db.execute(select(func.count(Alert.id)))
        total = total_result.scalar() or 0

        # Active
        active_result = await db.execute(
            select(func.count(Alert.id))
            .where(Alert.status == AlertStatusModel.ACTIVE)
        )
        active = active_result.scalar() or 0

        # By severity
        sev_result = await db.execute(
            select(Alert.severity, func.count(Alert.id))
            .group_by(Alert.severity)
        )
        by_severity = {
            (row[0].value if hasattr(row[0], "value") else str(row[0])): row[1]
            for row in sev_result.all()
        }

        # Recent active alerts (last 5)
        recent_result = await db.execute(
            select(Alert)
            .where(Alert.status == AlertStatusModel.ACTIVE)
            .order_by(desc(Alert.triggered_at))
            .limit(5)
        )
        recent_alerts = recent_result.scalars().all()

        recent = [
            {
                "alert_id": a.alert_id,
                "severity": a.severity.value if hasattr(a.severity, "value") else str(a.severity),
                "message": a.message or "",
                "risk_value": a.risk_value,
                "triggered_at": a.triggered_at.isoformat() + "Z" if a.triggered_at else None,
            }
            for a in recent_alerts
        ]

        return {
            "total": total,
            "active": active,
            "by_severity": by_severity,
            "recent": recent,
        }

    # ─────────────────────────────────────────────
    #  8. Infestation Hotspots
    # ─────────────────────────────────────────────
    async def _get_infestation_hotspots(self, db: AsyncSession) -> List[Dict[str, Any]]:
        """
        Tree locations with infestation data for heatmap rendering.
        Returns list of {tree_id, x, y, infestation_level, pest_name}.
        """
        from db.models import Tree, InfestationRecord, Pest

        result = await db.execute(
            select(
                Tree.tree_id,
                Tree.x_coordinate,
                Tree.y_coordinate,
                func.avg(InfestationRecord.infestation_level).label("avg_level"),
                func.count(InfestationRecord.infestation_id).label("record_count"),
                Pest.name.label("pest_name"),
            )
            .join(InfestationRecord, Tree.tree_id == InfestationRecord.tree_id)
            .join(Pest, InfestationRecord.pest_id == Pest.pest_id)
            .where(InfestationRecord.infected_status == True)  # noqa: E712
            .group_by(
                Tree.tree_id,
                Tree.x_coordinate,
                Tree.y_coordinate,
                Pest.name,
            )
            .order_by(desc("avg_level"))
            .limit(200)
        )
        rows = result.all()

        return [
            {
                "tree_id": row.tree_id,
                "x": float(row.x_coordinate) if row.x_coordinate else None,
                "y": float(row.y_coordinate) if row.y_coordinate else None,
                "avg_level": float(row.avg_level) if row.avg_level else 0,
                "record_count": row.record_count,
                "pest_name": row.pest_name,
            }
            for row in rows
        ]


# Singleton instance
monitoring_service = MonitoringService()
