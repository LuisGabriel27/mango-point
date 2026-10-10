"""
MangoPoint — Biological Dispersal Rules
========================================
Phenology-based rules informed by research, expert observations and orchard records.
Hourly lifecycle and activity coefficients remain provisional model assumptions.

Historical data analysis:
- Fruit fly (CPTD) peaks: May-July, with unmanaged orchards showing significantly higher pressure
- Cecid Fly activity: episodic, clustered around late dry season to early wet season transitions
  (particularly March to June), indicating rainfall-triggered emergence

Each pest species is modelled as a "gate" that opens or closes depending on:
- Orchard phenological stage (Dormant, Flowering, Fruitlet, Mature)
- Abiotic conditions (wind speed, temperature, rainfall, time of day)
- Biological triggers (rainfall accumulation for soil emergence, fruit ripeness)

Gate    │ Species              │ Stage Required │ Key Triggers
────────┼──────────────────────┼────────────────┼────────────────────────────────
Cecid   │ P. frugivora         │ FRUITLET       │ Soil emergence, twilight/cloudy daylight
Fruit   │ B. dorsalis          │ MATURE         │ Green mature/ripening fruit, solar activity

Operational Cecid runs track original soil cohorts and their remaining eggs;
new fruit infestations do not immediately become adult sources.
Dispersal probability decays with distance.
For Fruit Fly the probability is boosted in the downwind direction and by fruit ripeness.
"""

from __future__ import annotations

import math
from datetime import datetime
import numpy as np
from typing import Any, Callable, Dict, Hashable, List, Mapping, Optional, Tuple
from collections import deque

from core.config import (
    # Orchard stages
    OrchardStage,
    # Cecid Fly
    CECID_WIND_THRESHOLD_MS,
    CECID_BASE_DISPERSAL_PROB,
    CECID_DISTANCE_DECAY,
    CECID_MAX_RANGE_CELLS,
    CECID_RAINFALL_THRESHOLD_MM,
    CECID_RAIN_HISTORY_HOURS,
    CECID_NO_CURRENT_RAIN,
    CECID_SOIL_WETNESS_HALF_LIFE_HOURS,
    CECID_FAVORABLE_THRESHOLD,
    CECID_DRY_RAIN_MAX_MM,
    CECID_DRYING_ZERO_MM,
    CECID_ADULT_HALF_LIFE_HOURS,
    CECID_ADULT_MAX_AGE_HOURS,
    CECID_EGG_CAPACITY_HOURS,
    CECID_CLOUD_DAY_ACTIVITY_MAX,
    CECID_GENTLE_WIND_MAX_KMH,
    CECID_WIND_ACTIVITY_SCALE_KMH,
    CECID_WIND_DIRECTION_FULL_KMH,
    DAWN_START, DAWN_END,
    DUSK_START, DUSK_END,
    # Fruit Fly
    FRUIT_FLY_TEMP_THRESHOLD_C,
    FRUIT_FLY_BASE_DISPERSAL_PROB,
    FRUIT_FLY_WIND_BOOST,
    FRUIT_FLY_DISTANCE_DECAY,
    FRUIT_FLY_MAX_RANGE_CELLS,
    FRUIT_FLY_DAY_START,
    FRUIT_FLY_DAY_END,
    FRUIT_FLY_TWILIGHT_ACTIVITY,
    FRUIT_FLY_NIGHT_ACTIVITY,
    FRUIT_FLY_SUGAR_INDEX_MAX,
    NEIGHBOR_THREAT_WEIGHT,
    # General
    NEIGHBOUR_OFFSETS,
    NEIGHBOUR_ANGLES,
    CellState,
)
from core.cecid_habitat import (
    cecid_wind_activity,
    cecid_wind_assist_strength,
    cecid_wind_direction_factor,
)
from core.grid import OrchardGrid
from utils.datetime_utils import parse_rfc3339, format_rfc3339
from utils.solar import MANILA_TZ, solar_twilight_context
from utils.daylight import daylight_light_components, DAYLIGHT_WEATHER_FIELDS


# ─────────────────────────────────────────────
#  Helper: angular difference (handles wrap)
# ─────────────────────────────────────────────
def _angular_diff(a: float, b: float) -> float:
    """Smallest absolute angular difference in [0, 180]."""
    d = abs(a - b) % 360
    return d if d <= 180 else 360 - d


def _wind_toward_deg(wind_from_deg: float) -> float:
    """Convert meteorological wind-from degrees to the direction wind blows toward."""
    return (wind_from_deg + 180.0) % 360.0


def _chebyshev_offsets(max_range: int, include_angle: bool = False) -> tuple:
    """Precompute fixed neighbourhood offsets used by grid dispersal."""
    offsets = []
    for dr in range(-max_range, max_range + 1):
        for dc in range(-max_range, max_range + 1):
            if dr == 0 and dc == 0:
                continue
            dist = max(abs(dr), abs(dc))
            if include_angle:
                # GIS rows increase latitude (northward), so dr is the north
                # component and dc is the east component of the movement.
                target_angle = np.degrees(np.arctan2(dc, dr)) % 360
                offsets.append((dr, dc, dist, target_angle))
            else:
                offsets.append((dr, dc, dist))
    return tuple(offsets)


def _radial_offsets(max_range: int) -> tuple:
    """Offsets inside a true Euclidean radius (3 cells = 15 m)."""
    offsets = []
    for dr in range(-max_range, max_range + 1):
        for dc in range(-max_range, max_range + 1):
            if dr == 0 and dc == 0:
                continue
            distance = math.hypot(dr, dc)
            if distance <= max_range + 1e-9:
                offsets.append((dr, dc, distance))
    return tuple(offsets)


CECID_OFFSETS = _radial_offsets(CECID_MAX_RANGE_CELLS)
FRUIT_FLY_OFFSETS = _chebyshev_offsets(FRUIT_FLY_MAX_RANGE_CELLS, include_angle=True)


class CecidSourceCohortModel:
    """Track a finite soil reservoir and adults with remaining egg capacity.

    Each source contains one provisional emergence batch across antecedent
    replay and the forecast. Rain supplies a moisture proxy, not new insects.
    Adults decay with age, expire at 48 hours, and use normalized egg capacity
    when laying opportunities occur, independently of successful infestation.
    No measured insect or egg counts are implied by these pressure units.
    """

    def __init__(
        self,
        source_pressures: Mapping[Hashable, float],
        antecedent_rainfall: Optional[List[float]] = None,
        egg_capacity_hours: float = CECID_EGG_CAPACITY_HOURS,
    ) -> None:
        if not math.isfinite(egg_capacity_hours) or egg_capacity_hours <= 0.0:
            raise ValueError("egg_capacity_hours must be positive and finite")
        self.egg_capacity_hours = float(egg_capacity_hours)
        self.source_pressures = {
            key: max(0.0, float(pressure))
            for key, pressure in source_pressures.items()
            if float(pressure) > 0.0
        }
        # Retain the antecedent_rainfall argument for caller compatibility.
        # The gate's soil state controls emergence; no separate rain arming.
        self.remaining_soil_batches = {key: 1 for key in self.source_pressures}
        self.cohorts: Dict[Hashable, List[Dict[str, Any]]] = {
            key: [] for key in self.source_pressures
        }
        self.events: List[Dict[str, Any]] = []
        self._next_cohort_id = 1
        self.spent_cohort_count = 0
        self.expired_cohort_count = 0
        self.last_egg_capacity_used = 0.0

    def step(
        self,
        timestep: int,
        timestamp: Any,
        rainfall_mm: float,
        emergence_window_open: bool,
    ) -> Dict[Hashable, float]:
        """Advance cohorts by one hour and return active source pressures."""
        self.last_egg_capacity_used = 0.0
        for key, cohorts in self.cohorts.items():
            self.expired_cohort_count += sum(
                int(cohort["age"]) + 1 >= CECID_ADULT_MAX_AGE_HOURS
                for cohort in cohorts
            )
            self.cohorts[key] = [
                {**cohort, "age": int(cohort["age"]) + 1}
                for cohort in cohorts
                if int(cohort["age"]) + 1 < CECID_ADULT_MAX_AGE_HOURS
            ]

        # The caller evaluates moisture, current rain and activity separately.
        # A positive emergence window can release existing insects without
        # requiring a newly recorded rain event or a completely dry hour.
        if emergence_window_open:
            for key in self.source_pressures:
                if self.remaining_soil_batches[key] <= 0:
                    continue
                cohort_id = self._next_cohort_id
                self._next_cohort_id += 1
                self.cohorts[key].append({"id": cohort_id, "age": 0, "egg_capacity": 1.0})
                self.remaining_soil_batches[key] -= 1
                self.events.append({
                    "cohort_id": f"cecid-cohort-{cohort_id}",
                    "timestep": int(timestep),
                    "datetime": str(timestamp) if timestamp is not None else None,
                    "source": key,
                    "base_pressure": self.source_pressures[key],
                    "antecedent": int(timestep) < 0,
                    "initial_egg_capacity": 1.0,
                    "adult_max_age_hours": CECID_ADULT_MAX_AGE_HOURS,
                })

        active: Dict[Hashable, float] = {}
        for key, cohorts in self.cohorts.items():
            pressure = self.source_pressures[key] * sum(
                2.0 ** (-int(cohort["age"]) / CECID_ADULT_HALF_LIFE_HOURS)
                * float(cohort["egg_capacity"])
                for cohort in cohorts
            )
            if pressure > 0.0:
                active[key] = float(pressure)
        return active

    def active_cohorts(self) -> Dict[str, Dict[str, Any]]:
        """Return independently traceable cohorts for habitat relay movement."""
        active: Dict[str, Dict[str, Any]] = {}
        for source, cohorts in self.cohorts.items():
            base_pressure = self.source_pressures[source]
            for cohort in cohorts:
                age = int(cohort["age"])
                cohort_id = f"cecid-cohort-{int(cohort['id'])}"
                active[cohort_id] = {
                    "source": source,
                    "age_hours": age,
                    "remaining_egg_capacity": float(cohort["egg_capacity"]),
                    "pressure": base_pressure * (
                        2.0 ** (-age / CECID_ADULT_HALF_LIFE_HOURS)
                    ) * float(cohort["egg_capacity"]),
                }
        return active

    def consume_oviposition(self, opportunities: Mapping[str, float]) -> None:
        """Spend capacity before bagging/establishment and stochastic draws.

        Opportunity weights are pooled across all reachable fruit trees for
        each cohort. One target never automatically removes the whole group.
        The bounded per-hour rate is an explicit, uncalibrated assumption.
        """
        self.last_egg_capacity_used = 0.0
        for source, cohorts in self.cohorts.items():
            retained = []
            for cohort in cohorts:
                cohort_id = f"cecid-cohort-{int(cohort['id'])}"
                opportunity = min(1.0, max(0.0, float(opportunities.get(cohort_id, 0.0))))
                remaining = float(cohort["egg_capacity"])
                used = min(remaining, opportunity / self.egg_capacity_hours)
                cohort["egg_capacity"] = max(0.0, remaining - used)
                self.last_egg_capacity_used += used
                if cohort["egg_capacity"] <= 1e-12:
                    self.spent_cohort_count += 1
                else:
                    retained.append(cohort)
            self.cohorts[source] = retained

    def consume_source_opportunities(self, opportunities: Mapping[Hashable, float]) -> None:
        self.consume_oviposition({
            cohort_id: opportunities.get(cohort["source"], 0.0)
            for cohort_id, cohort in self.active_cohorts().items()
        })

    def consume_habitat_opportunities(
        self, contributions: Mapping[Hashable, list], base_probability: float,
        movement_score: float, source_factors: Mapping[Hashable, float],
    ) -> None:
        opportunities: Dict[str, float] = {}
        for arrivals in contributions.values():
            for arrival in arrivals:
                cohort_id = str(arrival["cohort_id"])
                weight = (
                    base_probability * movement_score
                    * max(0.0, float(arrival["path_efficiency"]))
                    * max(0.0, float(source_factors.get(arrival["source"], 1.0)))
                )
                opportunities[cohort_id] = opportunities.get(cohort_id, 0.0) + weight
        self.consume_oviposition(opportunities)

    def lifecycle_diagnostics(self) -> Dict[str, Any]:
        return {
            "active_laying_cohort_count": sum(len(cohorts) for cohorts in self.cohorts.values()),
            "remaining_soil_batches": sum(self.remaining_soil_batches.values()),
            "remaining_egg_capacity": sum(
                float(cohort["egg_capacity"])
                for cohorts in self.cohorts.values() for cohort in cohorts
            ),
            "egg_capacity_used_this_hour": self.last_egg_capacity_used,
            "spent_cohort_count": self.spent_cohort_count,
            "expired_cohort_count": self.expired_cohort_count,
        }

    def warm_up(
        self,
        antecedent_weather: List[Dict[str, Any]],
        emergence_window_open: Callable[[Dict[str, Any]], bool],
        step_observer: Optional[
            Callable[[Dict[str, Any], Dict[str, Dict[str, Any]], bool], None]
        ] = None,
    ) -> Dict[Hashable, float]:
        """Replay dated antecedent weather so Hour 0 inherits cohort state.

        A complete weather context is authoritative over the legacy rain-only
        constructor input. This prevents a source whose first eligible window
        already occurred before Hour 0 from emitting the same cohort again.
        """
        if not antecedent_weather:
            return {}
        self.cohorts = {key: [] for key in self.source_pressures}
        self.events = []
        self._next_cohort_id = 1
        self.remaining_soil_batches = {key: 1 for key in self.source_pressures}
        self.spent_cohort_count = 0
        self.expired_cohort_count = 0
        self.last_egg_capacity_used = 0.0
        active: Dict[Hashable, float] = {}
        count = len(antecedent_weather)
        for index, weather in enumerate(antecedent_weather):
            window_open = bool(emergence_window_open(weather))
            active = self.step(
                timestep=index - count,
                timestamp=weather.get("datetime"),
                rainfall_mm=float(weather.get("rainfall_mm", 0.0)),
                emergence_window_open=window_open,
            )
            if step_observer is not None:
                step_observer(weather, self.active_cohorts(), window_open)
        # The observer may spend eggs; return pressure after that consumption.
        active = {}
        for cohort in self.active_cohorts().values():
            source = cohort["source"]
            active[source] = active.get(source, 0.0) + float(cohort["pressure"])
        return active


# ═════════════════════════════════════════════
#  Base class
# ═════════════════════════════════════════════
class DispersalGate:
    """
    Abstract gate – subclasses implement `is_open` and `dispersal_prob`.

    The engine passes contextual information; all biological decisions
    are made within the gate classes to maintain clean modular architecture.

    Context passed by engine:
    - hour: current hour of day (0-23)
    - wind_speed_ms: wind speed in m/s
    - temperature_c: temperature in Celsius
    - rainfall_mm: current timestep rainfall
    - rainfall_history: deque of antecedent hourly rainfall (72 hours for Cecid)
    - orchard_stage: current phenological stage
    - sugar_index: fruit ripeness index (0-1)
    """

    # Subclasses override with the stage this gate requires of the SOURCE cell.
    # Used by `compute_dispersal_per_cell` to filter which infested cells can
    # disperse when phenology varies across the orchard.
    REQUIRED_STAGE: Optional[OrchardStage] = None

    def set_weather_context(self, weather: Mapping[str, Any]) -> None:
        """Pass optional weather fields without widening legacy gate signatures."""
        if hasattr(self, "set_time_context"):
            self.set_time_context(weather.get("datetime"))

    def _source_mask(self, grid: OrchardGrid) -> np.ndarray:
        return grid.infested_mask

    def is_open(
        self,
        hour: int,
        wind_speed_ms: float,
        temperature_c: float,
        rainfall_mm: float = 0.0,
        rainfall_history: Optional[deque] = None,
        orchard_stage: OrchardStage = OrchardStage.MATURE,
        sugar_index: float = 0.5,
    ) -> bool:
        raise NotImplementedError

    def compute_dispersal(
        self,
        grid: OrchardGrid,
        hour: int,
        wind_speed_ms: float,
        wind_dir_deg: float,
        temperature_c: float,
        rainfall_mm: float = 0.0,
        rainfall_history: Optional[deque] = None,
        orchard_stage: OrchardStage = OrchardStage.MATURE,
        sugar_index: float = 0.5,
    ) -> None:
        """
        For every INFESTED cell, accumulate dispersal probability onto
        susceptible neighbours.  Modifies `grid.risk` **in-place**.
        """
        if not self.is_open(
            hour, wind_speed_ms, temperature_c,
            rainfall_mm, rainfall_history, orchard_stage, sugar_index
        ):
            return  # gate closed – no dispersal this timestep

        if not grid.susceptible_mask.any():
            return

        infested_rows, infested_cols = np.where(self._source_mask(grid))
        for src_r, src_c in zip(infested_rows, infested_cols):
            self._spread_from(
                grid, src_r, src_c,
                wind_speed_ms, wind_dir_deg, temperature_c,
                rainfall_mm, rainfall_history, orchard_stage, sugar_index,
            )

    def compute_dispersal_per_cell(
        self,
        grid: OrchardGrid,
        stage_grid: np.ndarray,
        hour: int,
        wind_speed_ms: float,
        wind_dir_deg: float,
        temperature_c: float,
        rainfall_mm: float = 0.0,
        rainfall_history: Optional[deque] = None,
        sugar_index: float = 0.5,
    ) -> None:
        """
        Per-cell phenology variant of `compute_dispersal`.

        The environmental half of `is_open` still applies globally (wind, rain,
        hour, temperature), but the stage check is per source cell: only
        infested cells whose `stage_grid[r, c] == self.REQUIRED_STAGE` can
        disperse. This lets a single orchard carry mixed stages and still
        honour each gate's stage requirement.

        Uses the gate's own `REQUIRED_STAGE` for the `is_open` stage slot so
        the environmental checks fire as normal; the source-side filter is
        what actually gates dispersal spatially.
        """
        if self.REQUIRED_STAGE is None:
            # No stage requirement declared → fall back to scalar behaviour.
            self.compute_dispersal(
                grid, hour, wind_speed_ms, wind_dir_deg, temperature_c,
                rainfall_mm, rainfall_history, OrchardStage.MATURE, sugar_index,
            )
            return

        if not self.is_open(
            hour, wind_speed_ms, temperature_c,
            rainfall_mm, rainfall_history, self.REQUIRED_STAGE, sugar_index,
        ):
            return

        if not grid.susceptible_mask.any():
            return

        required_int = int(self.REQUIRED_STAGE)
        eligible = self._source_mask(grid) & (stage_grid == required_int)
        infested_rows, infested_cols = np.where(eligible)
        for src_r, src_c in zip(infested_rows, infested_cols):
            self._spread_from(
                grid, src_r, src_c,
                wind_speed_ms, wind_dir_deg, temperature_c,
                rainfall_mm, rainfall_history, self.REQUIRED_STAGE, sugar_index,
                target_stage_grid=stage_grid,
                required_stage_int=required_int,
            )

    def _spread_from(
        self,
        grid: OrchardGrid,
        src_r: int,
        src_c: int,
        wind_speed_ms: float,
        wind_dir_deg: float,
        temperature_c: float,
        rainfall_mm: float = 0.0,
        rainfall_history: Optional[deque] = None,
        orchard_stage: OrchardStage = OrchardStage.MATURE,
        sugar_index: float = 0.5,
        target_stage_grid: Optional[np.ndarray] = None,
        required_stage_int: Optional[int] = None,
    ) -> None:
        raise NotImplementedError


# ═════════════════════════════════════════════
#  Cecid Fly Gate
# ═════════════════════════════════════════════
class CecidFlyGate(DispersalGate):
    """
    Procontarinia frugivora – fruit-attacking Cecid only.

    Based on 2022-2025 historical data:
    - Activity is episodic, not continuous
    - Emergence events cluster around late dry to early wet season transitions
    - Larvae emerge from soil after rainfall to infest newly formed fruitlets

    Fruitlets are the host. Adults can move at solar dawn/dusk and during cloudy
    daylight (expert evidence). Rain-derived soil moisture affects emergence;
    existing adults' movement does not require another rain event.
    """

    REQUIRED_STAGE = OrchardStage.FRUITLET

    def __init__(
        self,
        rainfall_threshold_mm: Optional[float] = None,
        wind_threshold_ms: Optional[float] = None,
        base_dispersal_prob: Optional[float] = None,
        distance_decay: Optional[float] = None,
        latitude: float = 10.585,
        longitude: float = 122.580,
        favorable_threshold: float = CECID_FAVORABLE_THRESHOLD,
        initial_soil_moisture_score: Optional[float] = None,
    ):
        self.rainfall_threshold_mm = rainfall_threshold_mm if rainfall_threshold_mm is not None else CECID_RAINFALL_THRESHOLD_MM
        self.wind_threshold_ms = wind_threshold_ms if wind_threshold_ms is not None else CECID_WIND_THRESHOLD_MS
        self.base_dispersal_prob = base_dispersal_prob if base_dispersal_prob is not None else CECID_BASE_DISPERSAL_PROB
        self.distance_decay = distance_decay if distance_decay is not None else CECID_DISTANCE_DECAY
        self.latitude = float(latitude)
        self.longitude = float(longitude)
        self.favorable_threshold = float(favorable_threshold)
        self.current_datetime: Optional[datetime] = None
        self.current_hour: int = 0
        self.active_source_pressures: Optional[Dict[Tuple[int, int], float]] = None
        self.current_cloud_cover_pct: Optional[float] = None
        self.current_daylight_weather: Dict[str, Any] = {}
        self.oviposition_opportunities: Dict[Tuple[int, int], float] = {}
        if initial_soil_moisture_score is not None and (
            not math.isfinite(initial_soil_moisture_score)
            or not 0.0 <= initial_soil_moisture_score <= 1.0
        ):
            raise ValueError("initial_soil_moisture_score must be between 0 and 1")
        self.initial_soil_moisture_score = initial_soil_moisture_score
        self.simulation_step = 0

    def set_simulation_step(self, step: int) -> None:
        """Negative steps replay antecedent weather; zero is forecast Hour 0."""
        self.simulation_step = int(step)

    def set_weather_context(self, weather: Mapping[str, Any]) -> None:
        super().set_weather_context(weather)
        value = weather.get("cloud_cover_pct")
        try:
            cloud = float(value) if value is not None else None
            self.current_cloud_cover_pct = (
                max(0.0, min(100.0, cloud)) if cloud is not None and math.isfinite(cloud) else None
            )
        except (ValueError, TypeError):
            self.current_cloud_cover_pct = None
        self.current_daylight_weather = {key: weather.get(key) for key in DAYLIGHT_WEATHER_FIELDS}
        self.oviposition_opportunities = {}

    def set_time_context(self, value: Any) -> None:
        """Set the dated timestamp used for twilight and cloudy daylight."""
        if isinstance(value, datetime):
            resolved = value
        elif value:
            try:
                resolved = parse_rfc3339(str(value))
            except (TypeError, ValueError):
                resolved = None
        else:
            resolved = None
        if resolved is not None and resolved.tzinfo is None:
            resolved = resolved.replace(tzinfo=MANILA_TZ)
        self.current_datetime = resolved

    def soil_wetness(self, rainfall_history: Optional[deque]) -> float:
        """Rain proxy or an explicit Hour 0 state, plus subsequent rainfall.

        The initial score is a relative scenario state, not volumetric water
        content. It replaces the antecedent rain estimate at Hour 0, decays
        with the existing half-life, and never rewrites antecedent cohorts.
        """
        decay = 2.0 ** (-1.0 / CECID_SOIL_WETNESS_HALF_LIFE_HOURS)
        rainfall_values = list(rainfall_history or [])
        explicit_initial = (
            self.initial_soil_moisture_score is not None and self.simulation_step >= 0
        )
        if explicit_initial:
            rainfall_values = rainfall_values[-(self.simulation_step + 1):]
        wetness = 0.0
        for rainfall in rainfall_values:
            wetness = wetness * decay + max(0.0, float(rainfall))
        if explicit_initial:
            wetness += (
                float(self.initial_soil_moisture_score) * self.rainfall_threshold_mm
                * decay ** self.simulation_step
            )
        return float(wetness)

    def _twilight_context(self, hour: int) -> Dict[str, Any]:
        if self.current_datetime is None:
            is_crepuscular = (DAWN_START <= hour < DAWN_END) or (DUSK_START <= hour < DUSK_END)
            return {
                "is_crepuscular": is_crepuscular,
                "is_daylight": 6 <= hour < 18,
                "window": "dawn" if DAWN_START <= hour < DAWN_END else "dusk" if DUSK_START <= hour < DUSK_END else None,
                "sunrise": None,
                "sunset": None,
            }
        return solar_twilight_context(
            self.current_datetime,
            latitude=self.latitude,
            longitude=self.longitude,
            window_hours=1.0,
        )

    def suitability_components(
        self,
        wind_speed_ms: float,
        rainfall_mm: float,
        rainfall_history: Optional[deque],
        orchard_stage: OrchardStage,
        hour: int,
        cloud_cover_pct: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Return hard biological checks and soft weather suitability scores."""
        twilight = self._twilight_context(hour)
        cloud = self.current_cloud_cover_pct if cloud_cover_pct is None else cloud_cover_pct
        light = daylight_light_components(
            {**self.current_daylight_weather, "cloud_cover_pct": cloud},
            self.current_datetime, self.latitude, self.longitude,
        )
        cloudy_day_score = (
            CECID_CLOUD_DAY_ACTIVITY_MAX * light["daylight_light_score"]
            if twilight["is_daylight"] else 0.0
        )
        activity_score = 1.0 if twilight["is_crepuscular"] else cloudy_day_score
        hard_reasons: List[str] = []
        if orchard_stage != OrchardStage.FRUITLET:
            hard_reasons.append("fruitlet stage required")
        if activity_score <= 0.0:
            hard_reasons.append("outside solar dawn/dusk or supported dim/cloudy daylight activity")
            if twilight["is_daylight"] and light["daylight_light_limiting_reason"]:
                hard_reasons.append(light["daylight_light_limiting_reason"])

        wetness = self.soil_wetness(rainfall_history)
        moisture_score = min(1.0, wetness / max(self.rainfall_threshold_mm, 1e-9))
        current_rain = max(0.0, float(rainfall_mm))
        if current_rain <= CECID_DRY_RAIN_MAX_MM:
            drying_score = 1.0
        elif current_rain >= CECID_DRYING_ZERO_MM:
            drying_score = 0.0
        else:
            drying_score = (
                CECID_DRYING_ZERO_MM - current_rain
            ) / (CECID_DRYING_ZERO_MM - CECID_DRY_RAIN_MAX_MM)
        wind_activity = cecid_wind_activity(wind_speed_ms)
        wind_assist = cecid_wind_assist_strength(wind_speed_ms)
        emergence_score = moisture_score * drying_score * activity_score
        movement_score = drying_score * wind_activity * activity_score
        suitability = max(0.0, min(1.0, emergence_score * wind_activity))

        limiting: List[str] = []
        if moisture_score < 1.0:
            limiting.append("soil moisture below selected sensitivity scale")
        if drying_score < 1.0:
            limiting.append("current rain is suppressing emergence")
        if wind_activity < 0.75:
            limiting.append(
                "wind is limiting controlled flight; downwind movement may still be assisted"
            )

        sunrise = twilight.get("sunrise")
        if not twilight["is_crepuscular"] and twilight["is_daylight"]:
            limiting.append("daylight activity uses an uncalibrated light response")
        sunset = twilight.get("sunset")
        return {
            "hard_open": not hard_reasons,
            "hard_reasons": hard_reasons,
            "limiting_factors": limiting,
            "soil_wetness_mm": wetness,
            "soil_moisture_basis": (
                "assumed Hour 0 moisture plus forecast rain"
                if self.initial_soil_moisture_score is not None and self.simulation_step >= 0
                else "antecedent rainfall proxy"
            ),
            "initial_soil_moisture_score": self.initial_soil_moisture_score,
            "moisture_score": moisture_score,
            "drying_score": drying_score,
            "wind_score": wind_activity,
            "wind_activity_score": wind_activity,
            # Compatibility field retained for saved runs and older clients.
            "wind_survival_score": wind_activity,
            "wind_direction_assist": wind_assist,
            "wind_speed_kmh": max(0.0, float(wind_speed_ms)) * 3.6,
            "wind_no_penalty_max_kmh": CECID_GENTLE_WIND_MAX_KMH,
            "wind_activity_scale_kmh": CECID_WIND_ACTIVITY_SCALE_KMH,
            "wind_direction_full_kmh": CECID_WIND_DIRECTION_FULL_KMH,
            "wind_model": "soft inverse-square activity plus per-edge downwind bias",
            "downwind_bearing_deg": None,
            "suitability_score": suitability,
            "movement_score": movement_score,
            "emergence_score": emergence_score,
            "activity_score": activity_score,
            "activity_window": twilight.get("window") or ("cloudy_day" if cloudy_day_score > 0.0 else None),
            "cloud_cover_pct": cloud,
            "cloud_cover_available": cloud is not None,
            **light,
            "is_daylight": twilight["is_daylight"],
            "twilight_window": twilight.get("window"),
            "sunrise_local": format_rfc3339(sunrise) if sunrise is not None else None,
            "sunset_local": format_rfc3339(sunset) if sunset is not None else None,
        }

    def is_open(
        self,
        hour: int,
        wind_speed_ms: float,
        temperature_c: float,
        rainfall_mm: float = 0.0,
        rainfall_history: Optional[deque] = None,
        orchard_stage: OrchardStage = OrchardStage.MATURE,
        sugar_index: float = 0.5,
    ) -> bool:
        self.current_hour = int(hour)
        # Fruitlet phenology and twilight/cloudy daylight permit activity.
        # Rain and wind now modulate probability through suitability instead
        # of causing discontinuous all-or-nothing closures.
        return bool(self.suitability_components(
            wind_speed_ms=wind_speed_ms,
            rainfall_mm=rainfall_mm,
            rainfall_history=rainfall_history,
            orchard_stage=orchard_stage,
            hour=hour,
        )["hard_open"])

    def set_active_source_pressures(
        self,
        pressures: Optional[Mapping[Tuple[int, int], float]],
    ) -> None:
        """Set fixed soil-source cohort pressure for the current hour."""
        self.active_source_pressures = (
            None if pressures is None
            else {tuple(key): float(value) for key, value in pressures.items()}
        )

    def compute_dispersal(
        self,
        grid: OrchardGrid,
        hour: int,
        wind_speed_ms: float,
        wind_dir_deg: float,
        temperature_c: float,
        rainfall_mm: float = 0.0,
        rainfall_history: Optional[deque] = None,
        orchard_stage: OrchardStage = OrchardStage.MATURE,
        sugar_index: float = 0.5,
    ) -> None:
        if self.active_source_pressures is None:
            return super().compute_dispersal(
                grid, hour, wind_speed_ms, wind_dir_deg, temperature_c,
                rainfall_mm, rainfall_history, orchard_stage, sugar_index,
            )
        if not self.is_open(
            hour, wind_speed_ms, temperature_c, rainfall_mm,
            rainfall_history, orchard_stage, sugar_index,
        ):
            return
        for (src_r, src_c), pressure in self.active_source_pressures.items():
            self._spread_from(
                grid, src_r, src_c, wind_speed_ms, wind_dir_deg,
                temperature_c, rainfall_mm, rainfall_history, orchard_stage,
                sugar_index, source_pressure=pressure,
            )

    def compute_dispersal_per_cell(
        self,
        grid: OrchardGrid,
        stage_grid: np.ndarray,
        hour: int,
        wind_speed_ms: float,
        wind_dir_deg: float,
        temperature_c: float,
        rainfall_mm: float = 0.0,
        rainfall_history: Optional[deque] = None,
        sugar_index: float = 0.5,
    ) -> None:
        if self.active_source_pressures is None:
            return super().compute_dispersal_per_cell(
                grid, stage_grid, hour, wind_speed_ms, wind_dir_deg,
                temperature_c, rainfall_mm, rainfall_history, sugar_index,
            )
        if not self.is_open(
            hour, wind_speed_ms, temperature_c, rainfall_mm,
            rainfall_history, self.REQUIRED_STAGE, sugar_index,
        ):
            return
        required_int = int(self.REQUIRED_STAGE)
        for (src_r, src_c), pressure in self.active_source_pressures.items():
            self._spread_from(
                grid, src_r, src_c, wind_speed_ms, wind_dir_deg,
                temperature_c, rainfall_mm, rainfall_history,
                self.REQUIRED_STAGE, sugar_index,
                target_stage_grid=stage_grid,
                required_stage_int=required_int,
                source_pressure=pressure,
            )

    def _spread_from(
        self,
        grid: OrchardGrid,
        src_r: int,
        src_c: int,
        wind_speed_ms: float,
        wind_dir_deg: float,
        temperature_c: float,
        rainfall_mm: float = 0.0,
        rainfall_history: Optional[deque] = None,
        orchard_stage: OrchardStage = OrchardStage.MATURE,
        sugar_index: float = 0.5,
        target_stage_grid: Optional[np.ndarray] = None,
        required_stage_int: Optional[int] = None,
        source_pressure: float = 1.0,
    ) -> None:
        suitability = self.suitability_components(
            wind_speed_ms=wind_speed_ms,
            rainfall_mm=rainfall_mm,
            rainfall_history=rainfall_history,
            orchard_stage=orchard_stage,
            hour=(
                self.current_datetime.astimezone(MANILA_TZ).hour
                if self.current_datetime else self.current_hour
            ),
        )["movement_score"]
        source_factor = grid.get_source_treatment_factor(src_r, src_c)
        for dr, dc, dist in CECID_OFFSETS:
            tr, tc = src_r + dr, src_c + dc
            if not (0 <= tr < grid.rows and 0 <= tc < grid.cols):
                continue
            if grid.state[tr, tc] in (CellState.EMPTY, CellState.DEAD):
                continue
            if (
                target_stage_grid is not None
                and required_stage_int is not None
                and int(target_stage_grid[tr, tc]) != required_stage_int
            ):
                continue

            movement_bearing = (math.degrees(math.atan2(dc, dr)) + 360.0) % 360.0
            direction_factor = cecid_wind_direction_factor(
                wind_speed_ms,
                wind_dir_deg,
                movement_bearing,
            )
            path_efficiency = (self.distance_decay ** (dist - 1)) * direction_factor
            opportunity = self.base_dispersal_prob * path_efficiency * suitability * source_factor
            source_key = (int(src_r), int(src_c))
            self.oviposition_opportunities[source_key] = (
                self.oviposition_opportunities.get(source_key, 0.0) + opportunity
            )
            if grid.state[tr, tc] == CellState.INFESTED:
                continue
            prob = self.base_dispersal_prob * path_efficiency
            prob *= suitability
            prob *= max(0.0, float(source_pressure))
            prob *= source_factor

            neighbor_threat = grid.get_effective_neighbor_threat(tr, tc, wind_dir_deg)
            if neighbor_threat > 0.0:
                prob += (
                    neighbor_threat
                    * NEIGHBOR_THREAT_WEIGHT
                    * suitability
                    * min(1.0, max(0.0, float(source_pressure)))
                    * min(1.35, path_efficiency)
                    * source_factor
                )

            grid.apply_dispersal_probability(tr, tc, prob)


# ═════════════════════════════════════════════
#  Fruit Fly Gate
# ═════════════════════════════════════════════
class FruitFlyGate(DispersalGate):
    """Bactrocera dorsalis movement on mature, including green mature, fruit.

    Solar daylight gives full activity; twilight and darkness use explicitly
    assumed reduced weights. The default temperature response is continuous,
    while a supplied experimental temperature threshold remains a hard cutoff.
    Dark-period movement evidence does not measure orchard oviposition; the
    small night coefficient is an uncalibrated scenario allowance.
    """

    REQUIRED_STAGE = OrchardStage.MATURE

    def __init__(
        self,
        temp_threshold_c: Optional[float] = None,
        base_dispersal_prob: Optional[float] = None,
        distance_decay: Optional[float] = None,
        wind_boost: Optional[float] = None,
        latitude: float = 10.585,
        longitude: float = 122.580,
    ):
        self.temp_threshold_c = temp_threshold_c if temp_threshold_c is not None else FRUIT_FLY_TEMP_THRESHOLD_C
        self.base_dispersal_prob = base_dispersal_prob if base_dispersal_prob is not None else FRUIT_FLY_BASE_DISPERSAL_PROB
        self.distance_decay = distance_decay if distance_decay is not None else FRUIT_FLY_DISTANCE_DECAY
        self.wind_boost = wind_boost if wind_boost is not None else FRUIT_FLY_WIND_BOOST
        self.explicit_temp_threshold = temp_threshold_c is not None
        self.latitude = float(latitude)
        self.longitude = float(longitude)
        self.current_datetime: Optional[datetime] = None
        self.current_hour = 0
        self.current_activity_score = 1.0

    def set_time_context(self, value: Any) -> None:
        try:
            resolved = value if isinstance(value, datetime) else parse_rfc3339(str(value)) if value else None
            if resolved is not None and resolved.tzinfo is None:
                resolved = resolved.replace(tzinfo=MANILA_TZ)
            self.current_datetime = resolved
        except (ValueError, TypeError):
            self.current_datetime = None

    def activity_components(self, hour: int, temperature_c: float) -> Dict[str, Any]:
        if self.current_datetime is not None:
            solar = solar_twilight_context(self.current_datetime, self.latitude, self.longitude)
            daylight, twilight = solar["is_daylight"], solar["is_crepuscular"]
        else:
            daylight = FRUIT_FLY_DAY_START <= hour < FRUIT_FLY_DAY_END
            twilight = (FRUIT_FLY_DAY_START - 1 <= hour < FRUIT_FLY_DAY_START
                        or FRUIT_FLY_DAY_END <= hour < FRUIT_FLY_DAY_END + 1)
        time_score = 1.0 if daylight else FRUIT_FLY_TWILIGHT_ACTIVITY if twilight else FRUIT_FLY_NIGHT_ACTIVITY
        temperature_score = max(0.0, min(1.5, (temperature_c - self.temp_threshold_c) / 10.0 + 1.0))
        return {
            "activity_score": time_score,
            "temperature_score": temperature_score,
            "activity_window": "daylight" if daylight else "twilight" if twilight else "darkness",
            "night_activity_is_assumed": True,
        }

    def is_open(
        self,
        hour: int,
        wind_speed_ms: float,
        temperature_c: float,
        rainfall_mm: float = 0.0,
        rainfall_history: Optional[deque] = None,
        orchard_stage: OrchardStage = OrchardStage.MATURE,
        sugar_index: float = 0.5,
    ) -> bool:
        self.current_hour = int(hour)
        components = self.activity_components(hour, temperature_c)
        self.current_activity_score = float(components["activity_score"])
        # 1. Stage check: MUST be in MATURE stage
        if orchard_stage != OrchardStage.MATURE:
            return False
        
        # An explicitly requested experimental cutoff remains supported.
        # The default 25 C value is an activity reference, not a hard cutoff.
        if self.explicit_temp_threshold and temperature_c < self.temp_threshold_c:
            return False
        return components["activity_score"] > 0.0 and components["temperature_score"] > 0.0

    def compute_dispersal(
        self,
        grid: OrchardGrid,
        hour: int,
        wind_speed_ms: float,
        wind_dir_deg: float,
        temperature_c: float,
        rainfall_mm: float = 0.0,
        rainfall_history: Optional[deque] = None,
        orchard_stage: OrchardStage = OrchardStage.MATURE,
        sugar_index: float = 0.5,
        target_stage_grid: Optional[np.ndarray] = None,
        required_stage_int: Optional[int] = None,
    ) -> None:
        """Use the smaller of active sources or susceptible targets."""
        if not self.is_open(
            hour, wind_speed_ms, temperature_c,
            rainfall_mm, rainfall_history, orchard_stage, sugar_index
        ):
            return

        susceptible = grid.susceptible_mask
        if not susceptible.any():
            return

        infested = self._source_mask(grid)
        if int(infested.sum()) <= int(susceptible.sum()):
            infested_rows, infested_cols = np.where(infested)
            for src_r, src_c in zip(infested_rows, infested_cols):
                self._spread_from(
                    grid, src_r, src_c,
                    wind_speed_ms, wind_dir_deg, temperature_c,
                    rainfall_mm, rainfall_history, orchard_stage, sugar_index,
                )
            return

        target_rows, target_cols = np.where(susceptible)
        for target_r, target_c in zip(target_rows, target_cols):
            self._spread_to(
                grid, target_r, target_c,
                wind_speed_ms, wind_dir_deg, temperature_c,
                rainfall_mm, rainfall_history, orchard_stage, sugar_index,
            )

    def _spread_from(
        self,
        grid: OrchardGrid,
        src_r: int,
        src_c: int,
        wind_speed_ms: float,
        wind_dir_deg: float,
        temperature_c: float,
        rainfall_mm: float = 0.0,
        rainfall_history: Optional[deque] = None,
        orchard_stage: OrchardStage = OrchardStage.MATURE,
        sugar_index: float = 0.5,
        target_stage_grid: Optional[np.ndarray] = None,
        required_stage_int: Optional[int] = None,
    ) -> None:
        temp_factor = min(1.5, (temperature_c - self.temp_threshold_c) / 10.0 + 1.0)
        sugar_factor = sugar_index / FRUIT_FLY_SUGAR_INDEX_MAX
        ripeness_factor = 0.5 + 1.0 * sugar_factor
        source_factor = grid.get_source_treatment_factor(src_r, src_c)
        source_pressure = self._source_pressure(grid, src_r, src_c)
        for dr, dc, dist, target_angle in FRUIT_FLY_OFFSETS:
            tr, tc = src_r + dr, src_c + dc
            if not (0 <= tr < grid.rows and 0 <= tc < grid.cols):
                continue
            if grid.state[tr, tc] in (CellState.EMPTY, CellState.INFESTED, CellState.DEAD):
                continue
            if (
                target_stage_grid is not None
                and required_stage_int is not None
                and int(target_stage_grid[tr, tc]) != required_stage_int
            ):
                continue

            prob = self.base_dispersal_prob * (self.distance_decay ** (dist - 1))

            # Wind-direction bias: weather uses meteorological wind-FROM
            # degrees, while target_angle is the spread direction. Convert to
            # wind-TOWARD degrees before testing whether the target is downwind.
            downwind_deg = _wind_toward_deg(wind_dir_deg)
            ang_diff = _angular_diff(downwind_deg, target_angle)

            # Boost when target is downwind (small angular difference)
            if ang_diff < 45:
                prob += self.wind_boost * (1.0 - ang_diff / 45.0)

            # Temperature bonus (warmer -> more active)
            prob *= temp_factor

            # Sugar index factor: riper fruit = stronger attraction
            # Sugar index ranges from ~0.3 (just entering mature) to 1.0 (fully ripe)
            prob *= ripeness_factor  # ranges from 0.5x to 1.5x
            prob *= source_factor

            # Neighbor threat factor: amplified when wind blows FROM the
            # direction of the neighbouring orchard (pests carried inward).
            neighbor_threat = grid.get_effective_neighbor_threat(tr, tc, wind_dir_deg)
            if neighbor_threat > 0.0:
                threat_boost = neighbor_threat * NEIGHBOR_THREAT_WEIGHT
                prob += threat_boost

            grid.apply_dispersal_probability(
                tr, tc, prob * source_pressure
                * self.current_activity_score,
            )

    def _source_mask(self, grid: OrchardGrid) -> np.ndarray:
        return (
            (grid.freeze_fruitfly_sources() > 0.0)
            & (grid.state != CellState.DEAD)
            & (grid.state != CellState.EMPTY)
        )

    @staticmethod
    def _source_pressure(grid: OrchardGrid, row: int, col: int) -> float:
        return float(grid.freeze_fruitfly_sources()[row, col])

    def _spread_to(
        self,
        grid: OrchardGrid,
        target_r: int,
        target_c: int,
        wind_speed_ms: float,
        wind_dir_deg: float,
        temperature_c: float,
        rainfall_mm: float = 0.0,
        rainfall_history: Optional[deque] = None,
        orchard_stage: OrchardStage = OrchardStage.MATURE,
        sugar_index: float = 0.5,
    ) -> None:
        temp_factor = min(1.5, (temperature_c - self.temp_threshold_c) / 10.0 + 1.0)
        sugar_factor = sugar_index / FRUIT_FLY_SUGAR_INDEX_MAX
        ripeness_factor = 0.5 + 1.0 * sugar_factor

        source_mask = self._source_mask(grid)
        for dr, dc, dist, target_angle in FRUIT_FLY_OFFSETS:
            src_r, src_c = target_r - dr, target_c - dc
            if not (0 <= src_r < grid.rows and 0 <= src_c < grid.cols):
                continue
            if not source_mask[src_r, src_c]:
                continue

            source_pressure = self._source_pressure(grid, src_r, src_c)
            source_factor = grid.get_source_treatment_factor(src_r, src_c)
            prob = self.base_dispersal_prob * (self.distance_decay ** (dist - 1))

            downwind_deg = _wind_toward_deg(wind_dir_deg)
            ang_diff = _angular_diff(downwind_deg, target_angle)
            if ang_diff < 45:
                prob += self.wind_boost * (1.0 - ang_diff / 45.0)

            prob *= temp_factor
            prob *= ripeness_factor
            prob *= source_factor

            neighbor_threat = grid.get_effective_neighbor_threat(target_r, target_c, wind_dir_deg)
            if neighbor_threat > 0.0:
                threat_boost = neighbor_threat * NEIGHBOR_THREAT_WEIGHT
                prob += threat_boost

            grid.apply_dispersal_probability(
                target_r, target_c, prob * source_pressure
                * self.current_activity_score,
            )
