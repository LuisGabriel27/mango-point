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
        memory_alert = {
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
            "suggested_simulation_params": alert_data.suggested_simulation_params,
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
        }

        fingerprint = self.alert_fingerprint(memory_alert)
        for existing in self._memory_alerts:
            if (
                existing.get("status") == "active"
                and self.alert_fingerprint(existing) == fingerprint
            ):
                existing.update({
                    "triggered_at": memory_alert["triggered_at"],
                    "severity": memory_alert["severity"],
                    "risk_value": memory_alert["risk_value"],
                    "affected_cells": memory_alert["affected_cells"],
                    "affected_tree_ids": memory_alert["affected_tree_ids"],
                    "message": memory_alert["message"],
                    "centroid_lon": memory_alert["centroid_lon"],
                    "centroid_lat": memory_alert["centroid_lat"],
                    "recommended_actions": memory_alert["recommended_actions"],
                })
                logger.info(
                    "Updated existing in-memory alert %s instead of storing duplicate %s",
                    existing.get("alert_id"),
                    alert_data.alert_id,
                )
                return

        self._memory_alerts.append(memory_alert)
        logger.info(f"Stored alert {alert_data.alert_id} in memory (database unavailable)")
    
    def get_memory_alerts(
        self,
        status: Optional[str] = None,
        orchard_id: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], int, int]:
        """Get alerts from memory store."""
        alerts = self._dedupe_alert_items(self._memory_alerts)
        if status:
            alerts = [a for a in alerts if a["status"] == status]
        if orchard_id:
            alerts = [a for a in alerts if a.get("orchard_id") == orchard_id]

        active_alerts = self._dedupe_alert_items([
            a for a in self._memory_alerts
            if a["status"] == "active"
        ])
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

    @classmethod
    def alert_fingerprint(cls, alert: Any) -> Tuple[Any, ...]:
        """Return a stable key for one active operational alert."""

        def get_value(name: str, default: Any = None) -> Any:
            if isinstance(alert, dict):
                return alert.get(name, default)
            return getattr(alert, name, default)

        orchard_id = str(get_value("orchard_id") or "").strip().lower()
        zone_name = str(get_value("zone_name") or "").strip().lower()
        message = str(get_value("message") or "").strip().lower()
        alert_kind = "condition" if ("gate condition" in zone_name or "weather forecast" in zone_name) else "risk"

        tree_ids = tuple(sorted(
            str(tree_id)
            for tree_id in (get_value("affected_tree_ids") or [])
            if tree_id not in (None, "")
        ))

        cell_values = []
        for cell in get_value("affected_cells") or []:
            if isinstance(cell, dict):
                cell_values.append((cell.get("row"), cell.get("col")))
            else:
                cell_values.append(str(cell))
        cells = tuple(sorted(cell_values))

        if alert_kind == "condition":
            return (alert_kind, orchard_id, zone_name)
        return (alert_kind, orchard_id, zone_name, tree_ids, cells, message)

    @classmethod
    def _dedupe_alert_items(cls, alerts: Sequence[Any]) -> List[Any]:
        """Collapse duplicate active alerts while preserving list order."""
        unique: List[Any] = []
        seen_active: set[Tuple[Any, ...]] = set()

        for alert in alerts:
            status = alert.get("status") if isinstance(alert, dict) else getattr(alert, "status", None)
            status_value = status.value if hasattr(status, "value") else str(status or "")
            if status_value == "active":
                fingerprint = cls.alert_fingerprint(alert)
                if fingerprint in seen_active:
                    continue
                seen_active.add(fingerprint)
            unique.append(alert)

        return unique
    
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
        stage_grid: Optional[Any] = None,
        required_stage_value: Optional[int] = None,
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
        if stage_grid is not None and required_stage_value is not None:
            high_risk_unbagged = high_risk_unbagged & (stage_grid == int(required_stage_value))
        
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
        required_stage: Optional[str] = None,
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
        required_stage_norm = (
            str(required_stage).strip().lower().replace(" ", "_")
            if required_stage
            else None
        )

        for feature in features:
            props = feature.get("properties", {}) or {}

            if required_stage_norm:
                feature_stage = str(props.get("stage", "")).strip().lower().replace(" ", "_")
                if feature_stage and feature_stage != required_stage_norm:
                    continue

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
            if (
                entry.get("status") == "favorable"
                if "status" in entry
                else bool(entry.get("gate_open"))
            )
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
                f"Expected Time: {first_window}. "
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

    def check_weather_forecast_alerts(
        self,
        forecast: List[Dict[str, Any]],
        orchard_id: str,
        lat: float,
        lon: float,
        orchard_stage: Optional[str] = None,
        monitored_pest_types: Optional[List[str]] = None,
        antecedent: Optional[List[Dict[str, Any]]] = None,
        provenance: Optional[Dict[str, Any]] = None,
    ) -> List["AlertCreate"]:
        """
        Analyze a 48-hour weather forecast for upcoming rain events and return
        pre-emptive pest alerts with suggested simulation parameters attached.

        Rain is the primary environmental trigger for both Cecid Fly (fruitlet
        stage) and Fruit Fly (mature stage). When rain is forecast, this method
        creates condition-style alerts so growers can run an informed simulation
        before the rain arrives rather than reacting after the fact.

        Parameters
        ----------
        forecast : list[dict]
            Hourly forecast from ``weather_service.get_forecast()``.
        orchard_id : str
            Identifier of the orchard.
        lat, lon : float
            Orchard coordinates (used as alert centroid).
        orchard_stage : str, optional
            Current phenological stage.  When supplied, only alerts for pests
            that are active at this stage are generated.
        monitored_pest_types : list[str], optional
            Pests to evaluate; defaults to ["cecid", "fruitfly"].
        """
        return self._check_weather_suitability_alerts(
            forecast=forecast,
            antecedent=antecedent or [],
            provenance=provenance or {},
            orchard_id=orchard_id,
            lat=lat,
            lon=lon,
            orchard_stage=orchard_stage,
            monitored_pest_types=monitored_pest_types,
        )

        # Legacy rain-only implementation retained below for compatibility
        # reference; execution uses the shared biological suitability model.
        RAIN_MM_THRESHOLD = 0.5  # mm/h minimum to flag as a rain event

        rain_hours = [
            f for f in forecast
            if float(f.get("rainfall_mm", 0) or 0) >= RAIN_MM_THRESHOLD
        ]
        if not rain_hours:
            return []

        peak_rain = max(float(f.get("rainfall_mm", 0) or 0) for f in rain_hours)
        total_rain_hours = len(rain_hours)
        cumulative_rain = sum(float(f.get("rainfall_mm", 0) or 0) for f in rain_hours)
        first_dt_raw = rain_hours[0].get("datetime", "soon")
        first_dt = self._friendly_eta(first_dt_raw)

        if peak_rain >= 10.0 or total_rain_hours >= 12:
            severity = AlertSeverityEnum.HIGH
        elif peak_rain >= 3.0 or total_rain_hours >= 4:
            severity = AlertSeverityEnum.MEDIUM
        else:
            severity = AlertSeverityEnum.LOW

        # Higher neighbor pressure when rain is widespread (≥ 20 mm total)
        neighbor_threat_value = round(0.3 if cumulative_rain >= 20.0 else 0.1, 1)

        pest_types = monitored_pest_types or ["cecid", "fruitfly"]

        # Stage-gating: filter to pests that are active at the current stage
        stage_pest_map: Dict[str, List[str]] = {
            "fruitlet": ["cecid"],
            "mature": ["fruitfly"],
            "dormant": [],
            "flowering": [],
        }
        if orchard_stage and orchard_stage in stage_pest_map:
            relevant_pests = [p for p in pest_types if p in stage_pest_map[orchard_stage]]
            if not relevant_pests:
                return []
        else:
            relevant_pests = pest_types

        hours_word = "hour" if total_rain_hours == 1 else "hours"
        alerts = []

        for pest in relevant_pests:
            pest_lower = str(pest).strip().lower().replace("-", "_")
            pest_label = self._pest_label(pest)
            is_cecid = "cecid" in pest_lower

            if is_cecid:
                suggested_stage = orchard_stage if orchard_stage == "fruitlet" else "fruitlet"
                suggested_days = 30
                prefix_rain = round(min(cumulative_rain, 24.0), 1)
                stage_note = (
                    "Cecid fly infestations peak 1–3 days after rainfall on fruitlet-stage trees."
                )
            else:
                suggested_stage = orchard_stage if orchard_stage == "mature" else "mature"
                suggested_days = 80
                prefix_rain = 0.0
                stage_note = (
                    "Fruit fly activity intensifies during warm, humid post-rain conditions near harvest."
                )

            suggested_params: Dict[str, Any] = {
                "pest_type": "cecid" if is_cecid else "fruitfly",
                "orchard_stage": suggested_stage,
                "hours": min(48, len(forecast)),
                "days_since_flowering": suggested_days,
                "neighbor_threat": neighbor_threat_value,
                "manual_weather_prefix_rain": prefix_rain,
                "_rain_summary": (
                    f"Rain forecast: {total_rain_hours} {hours_word} of rainfall in the next 48 h "
                    f"(peak {peak_rain:.1f} mm/h). Parameters pre-configured for {pest_label} risk."
                ),
            }

            message = (
                f"Rain forecast for the next 48 hours: {total_rain_hours} {hours_word} of rainfall "
                f"(peak {peak_rain:.1f} mm/h). Expected Time: {first_dt}. "
                f"{stage_note} "
                f"Simulation parameters have been pre-configured — run a forecast now to assess "
                f"orchard '{orchard_id}' risk before the rain arrives."
            )

            alert = AlertCreate(
                alert_id=f"alert_wx_{pest_lower[:6]}_{uuid.uuid4().hex[:10]}",
                simulation_run_id=None,
                severity=severity,
                risk_value=round(min(peak_rain / 25.0, 1.0), 4),
                affected_cells=[],
                affected_tree_ids=[],
                orchard_id=orchard_id,
                zone_name=f"{pest_label} weather forecast",
                message=message,
                centroid_lat=lat,
                centroid_lon=lon,
                recommended_actions=self._recommended_actions(
                    alert_kind="condition",
                    pest_type=pest,
                ),
                suggested_simulation_params=suggested_params,
            )
            alerts.append(alert)

            logger.info(
                "Weather forecast alert generated: %s, %d %s of rain (peak %.1f mm/h) for %s",
                pest_label,
                total_rain_hours,
                hours_word,
                peak_rain,
                orchard_id,
            )

        return alerts

    def _check_weather_suitability_alerts(
        self,
        forecast: List[Dict[str, Any]],
        antecedent: List[Dict[str, Any]],
        provenance: Dict[str, Any],
        orchard_id: str,
        lat: float,
        lon: float,
        orchard_stage: Optional[str],
        monitored_pest_types: Optional[List[str]],
    ) -> List[AlertCreate]:
        """Create alerts from the same suitability diagnostics as simulations."""
        from utils.weather_builder import compute_gate_diagnostics

        if not forecast:
            return []
        stage = str(orchard_stage or "mature").strip().lower()
        pest_types = monitored_pest_types or ["cecid", "fruitfly"]
        stage_pest_map = {
            "fruitlet": {"cecid"},
            "mature": {"fruitfly"},
            "dormant": set(),
            "flowering": set(),
        }
        if stage in stage_pest_map:
            pest_types = [pest for pest in pest_types if pest in stage_pest_map[stage]]

        antecedent_rain = [
            float(entry.get("rainfall_mm", 0.0)) for entry in antecedent
        ]
        provider = str(provenance.get("provider") or provenance.get("source") or "weather provider")
        alerts: List[AlertCreate] = []
        for pest in pest_types:
            diagnostics = compute_gate_diagnostics(
                weather_data=forecast,
                pest_type=pest,
                orchard_stage=stage,
                initial_rainfall_history=antecedent_rain,
                history_hours=72,
                latitude=lat,
                longitude=lon,
            )
            favorable = [entry for entry in diagnostics if entry.get("status") == "favorable"]
            if not favorable:
                continue

            count = len(favorable)
            fraction = count / max(1, len(diagnostics))
            peak_score = max(float(entry.get("suitability_score", 0.0)) for entry in favorable)
            pest_label = self._pest_label(pest)
            first_window = self._gate_window_label(favorable[0])
            severity = self._classify_gate_condition_severity(count, fraction)
            suggested_params: Dict[str, Any] = {
                "pest_type": pest,
                "orchard_stage": stage,
                "hours": min(168, len(forecast)),
                "weather_mode": "live",
                "_weather_provenance": provenance,
            }
            alerts.append(AlertCreate(
                alert_id=f"alert_wx_{str(pest)[:6]}_{uuid.uuid4().hex[:10]}",
                simulation_run_id=None,
                severity=severity,
                risk_value=round(peak_score, 4),
                affected_cells=[],
                affected_tree_ids=[],
                orchard_id=orchard_id,
                zone_name=f"{pest_label} weather forecast",
                message=(
                    f"{pest_label} conditions are favorable for {count} of "
                    f"{len(diagnostics)} forecast hour(s). Expected Time: "
                    f"{first_window}. Weather source: {provider}. Run the live "
                    f"simulation for orchard '{orchard_id}' and inspect susceptible trees."
                ),
                centroid_lat=lat,
                centroid_lon=lon,
                recommended_actions=self._recommended_actions(
                    alert_kind="condition", pest_type=pest,
                ),
                suggested_simulation_params=suggested_params,
            ))
        return alerts

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
    def _friendly_eta(dt_value: Any) -> str:
        """Convert a datetime string or object to a human-friendly ETA label.

        Examples:
            "2026-07-06T08:00:00Z"  → "today at 4:00 PM" (if today in +08)
            "2026-07-07T13:00:00Z"  → "tomorrow at 9:00 PM"
            "2026-07-10T06:00:00Z"  → "Jul 10 at 2:00 PM"
        """
        if not dt_value:
            return "soon"

        raw = str(dt_value)
        try:
            # Parse ISO 8601 — handles both 'Z' suffix and '+00:00'
            cleaned = raw.replace("Z", "+00:00")
            dt = datetime.fromisoformat(cleaned)
            now = datetime.now(dt.tzinfo)

            delta_days = (dt.date() - now.date()).days
            # Windows doesn't support '%-I', so always use %I and strip the leading zero
            time_str = dt.strftime("%I:%M %p").lstrip("0")

            if delta_days == 0:
                return f"today at {time_str}"
            elif delta_days == 1:
                return f"tomorrow at {time_str}"
            elif delta_days == -1:
                return f"yesterday at {time_str}"
            else:
                date_str = dt.strftime("%b %d").replace(" 0", " ")
                return f"{date_str} at {time_str}"
        except (ValueError, TypeError):
            # If parsing fails, return the raw value as-is
            return raw

    def _gate_window_label(self, entry: Dict[str, Any]) -> str:
        """Return a compact label for the first favorable forecast hour."""
        dt_value = entry.get("datetime")
        if dt_value:
            return self._friendly_eta(dt_value)

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
        duplicate = await self._find_active_duplicate_alert(db, alert_data)
        if duplicate is not None:
            logger.info(
                "Reusing existing active alert %s instead of creating duplicate %s",
                duplicate.alert_id,
                alert_data.alert_id,
            )
            return duplicate

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
            suggested_simulation_params=alert_data.suggested_simulation_params,
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

    async def _find_active_duplicate_alert(
        self,
        db: AsyncSession,
        alert_data: AlertCreate,
    ) -> Optional[Alert]:
        """Find an existing active alert with the same operational meaning."""
        execute = getattr(db, "execute", None)
        if execute is None:
            return None

        query = (
            select(Alert)
            .where(
                Alert.status == AlertStatus.ACTIVE,
                Alert.orchard_id == alert_data.orchard_id,
                Alert.zone_name == alert_data.zone_name,
            )
            .order_by(Alert.triggered_at.desc(), Alert.id.desc())
        )
        result = await execute(query)
        fingerprint = self.alert_fingerprint(alert_data)

        for existing in result.scalars().all():
            if self.alert_fingerprint(existing) == fingerprint:
                return existing

        return None
    
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
        query = select(Alert).order_by(Alert.triggered_at.desc(), Alert.id.desc())
        active_query = (
            select(Alert)
            .where(Alert.status == AlertStatus.ACTIVE)
            .order_by(Alert.triggered_at.desc(), Alert.id.desc())
        )
        
        if status:
            query = query.where(Alert.status == status)
        if orchard_id:
            query = query.where(Alert.orchard_id == orchard_id)
            active_query = active_query.where(Alert.orchard_id == orchard_id)

        result = await db.execute(query)
        matching_alerts = self._dedupe_alert_items(result.scalars().all())
        total_count = len(matching_alerts)
        alerts = matching_alerts[offset:offset + limit]
        
        active_result = await db.execute(active_query)
        active_count = len(self._dedupe_alert_items(active_result.scalars().all()))
        
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
