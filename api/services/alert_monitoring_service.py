"""
MangoPoint API - Alert Monitoring Service
=========================================
Scheduled orchard-aware checks for biological gate alerts.
"""

import asyncio
import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from .alert_service import alert_service
from .weather_service import weather_service
from db.models import Alert, AlertStatus, Orchard
from utils.datetime_utils import format_rfc3339, utcnow_naive
from utils.weather_builder import compute_gate_diagnostics

logger = logging.getLogger(__name__)


class AlertMonitoringService:
    """Run forecast-based biological gate checks for registered orchards."""

    def __init__(self) -> None:
        self._running = False
        self.last_run_summary: Optional[Dict[str, Any]] = None

    def status(self) -> Dict[str, Any]:
        """Return scheduler configuration and latest run summary."""
        return {
            "enabled": settings.ALERT_MONITORING_ENABLED,
            "running": self._running,
            "interval_seconds": settings.ALERT_MONITORING_INTERVAL_SECONDS,
            "forecast_hours": settings.ALERT_MONITORING_FORECAST_HOURS,
            "dedupe_hours": settings.ALERT_MONITORING_DEDUPE_HOURS,
            "last_run": self.last_run_summary,
        }

    async def run_scheduler(self) -> None:
        """Loop forever until cancelled, scanning orchards at the configured interval."""
        from ..core.database import async_session_maker

        self._running = True
        logger.info(
            "Starting orchard alert monitor every %d seconds",
            settings.ALERT_MONITORING_INTERVAL_SECONDS,
        )

        try:
            while self._running:
                try:
                    async with async_session_maker() as db:
                        summary = await self.scan_orchards(db)
                        await db.commit()
                        self.last_run_summary = summary
                        logger.info("Scheduled orchard alert scan complete: %s", summary)
                except Exception as exc:
                    logger.warning("Scheduled orchard alert scan failed: %s", exc)

                await asyncio.sleep(settings.ALERT_MONITORING_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            logger.info("Orchard alert monitor cancelled")
            raise
        finally:
            self._running = False

    def stop(self) -> None:
        """Request scheduler shutdown."""
        self._running = False

    async def scan_orchards(
        self,
        db: AsyncSession,
        orchard_id: Optional[str] = None,
        hours: Optional[int] = None,
        send_notifications: bool = True,
        dedupe_hours: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Scan active monitored orchards and create condition alerts."""
        scan_hours = hours or settings.ALERT_MONITORING_FORECAST_HOURS
        dedupe = (
            settings.ALERT_MONITORING_DEDUPE_HOURS
            if dedupe_hours is None
            else dedupe_hours
        )
        started_at = utcnow_naive()

        query = select(Orchard).where(
            Orchard.is_active.is_(True),
            Orchard.monitoring_enabled.is_(True),
        )
        if orchard_id:
            orchard_filter = [Orchard.orchard_uid == orchard_id]
            if str(orchard_id).isdigit():
                orchard_filter.append(Orchard.orchard_id == int(orchard_id))
            query = query.where(or_(*orchard_filter))

        result = await db.execute(query.order_by(Orchard.name.asc()))
        orchards = result.scalars().all()

        summary: Dict[str, Any] = {
            "scanned_at": format_rfc3339(started_at),
            "forecast_hours": scan_hours,
            "orchards_checked": len(orchards),
            "alerts_created": 0,
            "duplicates_skipped": 0,
            "failures": [],
            "orchards": [],
        }

        for orchard in orchards:
            try:
                orchard_summary = await self.scan_orchard(
                    db=db,
                    orchard=orchard,
                    hours=scan_hours,
                    send_notifications=send_notifications,
                    dedupe_hours=dedupe,
                )
                summary["orchards"].append(orchard_summary)
                summary["alerts_created"] += orchard_summary["alerts_created"]
                summary["duplicates_skipped"] += orchard_summary["duplicates_skipped"]
            except Exception as exc:
                failure = {
                    "orchard_id": orchard.orchard_uid or str(orchard.orchard_id),
                    "error": str(exc),
                }
                summary["failures"].append(failure)
                logger.warning("Orchard alert scan failed for %s: %s", failure["orchard_id"], exc)

        self.last_run_summary = summary
        return summary

    async def scan_orchard(
        self,
        db: AsyncSession,
        orchard: Orchard,
        hours: int,
        send_notifications: bool = True,
        dedupe_hours: int = 6,
    ) -> Dict[str, Any]:
        """Scan a single orchard for biological gate condition alerts."""
        orchard_uid = orchard.orchard_uid or str(orchard.orchard_id)
        lon, lat = self._orchard_coordinates(orchard)
        used_default_coordinates = lon is None or lat is None
        if used_default_coordinates:
            lon, lat = settings.DEFAULT_LON, settings.DEFAULT_LAT

        weather_bundle = await weather_service.get_forecast_bundle(
            lat=float(lat),
            lon=float(lon),
            hours=hours,
        )
        weather_data = weather_bundle["forecast"]
        antecedent = weather_bundle.get("antecedent", [])
        provenance = weather_bundle.get("provenance", {})

        pest_types = self._monitored_pest_types(orchard.monitored_pest_types)
        stage = orchard.orchard_stage or "mature"
        sugar_index = self._sugar_index_from_days(orchard.days_since_flowering)
        orchard_summary: Dict[str, Any] = {
            "orchard_id": orchard_uid,
            "name": orchard.name,
            "coordinates": {"lon": float(lon), "lat": float(lat)},
            "used_default_coordinates": used_default_coordinates,
            "stage": stage,
            "pests_checked": pest_types,
            "alerts_created": 0,
            "duplicates_skipped": 0,
            "gate_open": {},
            "alert_ids": [],
            "weather_provenance": provenance,
        }

        for pest_type in pest_types:
            diagnostics = compute_gate_diagnostics(
                weather_data=weather_data,
                pest_type=pest_type,
                orchard_stage=stage,
                sugar_index=sugar_index,
                initial_rainfall_history=[
                    float(entry.get("rainfall_mm", 0.0)) for entry in antecedent
                ],
                history_hours=72,
                latitude=float(lat),
                longitude=float(lon),
            )
            open_count = sum(
                1 for entry in diagnostics
                if entry.get("status") == "favorable"
            )
            orchard_summary["gate_open"][pest_type] = open_count

            alerts = alert_service.check_gate_condition_alerts(
                diagnostics=diagnostics,
                orchard_id=orchard_uid,
                simulation_run_id=None,
                pest_type=pest_type,
                orchard_stage=stage,
            )

            for alert_data in alerts:
                if dedupe_hours > 0 and await self._recent_active_alert_exists(
                    db=db,
                    orchard_id=orchard_uid,
                    zone_name=alert_data.zone_name,
                    dedupe_hours=dedupe_hours,
                ):
                    orchard_summary["duplicates_skipped"] += 1
                    continue

                alert = await alert_service.create_alert(
                    db=db,
                    alert_data=alert_data,
                    send_notifications=send_notifications,
                )
                orchard_summary["alerts_created"] += 1
                orchard_summary["alert_ids"].append(alert.alert_id)

        orchard.last_monitoring_scan_at = utcnow_naive()
        await db.flush()
        return orchard_summary

    async def _recent_active_alert_exists(
        self,
        db: AsyncSession,
        orchard_id: str,
        zone_name: Optional[str],
        dedupe_hours: int,
    ) -> bool:
        """Return True if a recent active condition alert already exists."""
        since = utcnow_naive() - timedelta(hours=dedupe_hours)
        result = await db.execute(
            select(Alert.alert_id)
            .where(
                Alert.orchard_id == orchard_id,
                Alert.zone_name == zone_name,
                Alert.status == AlertStatus.ACTIVE,
                Alert.triggered_at >= since,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    def _monitored_pest_types(value: Any) -> List[str]:
        """Normalize orchard monitoring pest config."""
        if not value:
            return ["cecid", "fruitfly"]

        if isinstance(value, str):
            raw_values: Sequence[Any] = [part.strip() for part in value.split(",")]
        else:
            raw_values = value

        allowed = {"cecid", "fruitfly"}
        out: List[str] = []
        for item in raw_values:
            normalized = str(getattr(item, "value", item)).strip().lower()
            if normalized in allowed and normalized not in out:
                out.append(normalized)

        return out or ["cecid", "fruitfly"]

    @staticmethod
    def _sugar_index_from_days(days_since_flowering: Optional[int]) -> float:
        """Mirror the simulation engine's fruit sugar-index initialization."""
        from core.config import (
            FRUIT_FLY_DEFAULT_DAYS_FLOWERING,
            FRUIT_FLY_SUGAR_INDEX_GROWTH,
            FRUIT_FLY_SUGAR_INDEX_MAX,
            FRUIT_FLY_SUGAR_INDEX_START,
        )

        days = (
            FRUIT_FLY_DEFAULT_DAYS_FLOWERING
            if days_since_flowering is None
            else max(0, int(days_since_flowering))
        )
        return min(
            FRUIT_FLY_SUGAR_INDEX_MAX,
            FRUIT_FLY_SUGAR_INDEX_START + (days * FRUIT_FLY_SUGAR_INDEX_GROWTH),
        )

    @staticmethod
    def _orchard_coordinates(
        orchard: Orchard,
    ) -> Tuple[Optional[float], Optional[float]]:
        """Get orchard monitoring coordinates from centroid or GeoJSON."""
        if orchard.centroid_lon is not None and orchard.centroid_lat is not None:
            return float(orchard.centroid_lon), float(orchard.centroid_lat)

        return _derive_geojson_centroid(orchard.geojson)


def _derive_geojson_centroid(
    geojson: Optional[Dict[str, Any]],
) -> Tuple[Optional[float], Optional[float]]:
    """Small service-local centroid fallback for older orchard records."""
    if not geojson:
        return None, None

    coords: List[Tuple[float, float]] = []
    for feature in geojson.get("features", []) or []:
        geometry = feature.get("geometry", {}) or {}
        geom_type = geometry.get("type")
        coordinates = geometry.get("coordinates")

        if geom_type == "Point":
            pair = _lon_lat_pair(coordinates)
            if pair:
                coords.append(pair)
        elif geom_type == "Polygon" and coordinates:
            ring = coordinates[0] or []
            if len(ring) > 1 and ring[0] == ring[-1]:
                ring = ring[:-1]
            for coord in ring:
                pair = _lon_lat_pair(coord)
                if pair:
                    coords.append(pair)

    if not coords:
        return None, None

    return (
        sum(coord[0] for coord in coords) / len(coords),
        sum(coord[1] for coord in coords) / len(coords),
    )


def _lon_lat_pair(value: Any) -> Optional[Tuple[float, float]]:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    try:
        return float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None


alert_monitoring_service = AlertMonitoringService()
