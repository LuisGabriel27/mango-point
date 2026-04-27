"""
MangoPoint — Biological Dispersal Rules
========================================
Phenology- and data-calibrated biological trigger system grounded in 2022-2025 orchard records.

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
Cecid   │ Mango Gall Midge     │ FRUITLET       │ Rainfall-triggered emergence, crepuscular
Fruit   │ Bactrocera spp.      │ MATURE         │ Sugar index (fruit ripeness), neighbor threat

When the gate is open the pest disperses from every INFESTED cell to
neighbouring cells.  Dispersal probability decays with distance.
For Fruit Fly the probability is boosted in the downwind direction and by fruit ripeness.
"""

from __future__ import annotations

import numpy as np
from typing import Optional, List
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
    FRUIT_FLY_SUGAR_INDEX_MAX,
    NEIGHBOR_THREAT_WEIGHT,
    # General
    NEIGHBOUR_OFFSETS,
    NEIGHBOUR_ANGLES,
    CellState,
)
from core.grid import OrchardGrid


# ─────────────────────────────────────────────
#  Helper: angular difference (handles wrap)
# ─────────────────────────────────────────────
def _angular_diff(a: float, b: float) -> float:
    """Smallest absolute angular difference in [0, 180]."""
    d = abs(a - b) % 360
    return d if d <= 180 else 360 - d


def _chebyshev_offsets(max_range: int, include_angle: bool = False) -> tuple:
    """Precompute fixed neighbourhood offsets used by grid dispersal."""
    offsets = []
    for dr in range(-max_range, max_range + 1):
        for dc in range(-max_range, max_range + 1):
            if dr == 0 and dc == 0:
                continue
            dist = max(abs(dr), abs(dc))
            if include_angle:
                target_angle = np.degrees(np.arctan2(dc, -dr)) % 360
                offsets.append((dr, dc, dist, target_angle))
            else:
                offsets.append((dr, dc, dist))
    return tuple(offsets)


CECID_OFFSETS = _chebyshev_offsets(CECID_MAX_RANGE_CELLS)
FRUIT_FLY_OFFSETS = _chebyshev_offsets(FRUIT_FLY_MAX_RANGE_CELLS, include_angle=True)


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
    - rainfall_history: deque of last 24 hours of rainfall
    - orchard_stage: current phenological stage
    - sugar_index: fruit ripeness index (0-1)
    """

    # Subclasses override with the stage this gate requires of the SOURCE cell.
    # Used by `compute_dispersal_per_cell` to filter which infested cells can
    # disperse when phenology varies across the orchard.
    REQUIRED_STAGE: Optional[OrchardStage] = None

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

        infested_rows, infested_cols = np.where(grid.infested_mask)
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
        eligible = grid.infested_mask & (stage_grid == required_int)
        infested_rows, infested_cols = np.where(eligible)
        for src_r, src_c in zip(infested_rows, infested_cols):
            self._spread_from(
                grid, src_r, src_c,
                wind_speed_ms, wind_dir_deg, temperature_c,
                rainfall_mm, rainfall_history, self.REQUIRED_STAGE, sugar_index,
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
    ) -> None:
        raise NotImplementedError


# ═════════════════════════════════════════════
#  Cecid Fly Gate
# ═════════════════════════════════════════════
class CecidFlyGate(DispersalGate):
    """
    Mango Gall Midge – phenology-calibrated, rainfall-triggered emergence.
    
    Based on 2022-2025 historical data:
    - Activity is episodic, not continuous
    - Emergence events cluster around late dry to early wet season transitions
    - Larvae emerge from soil after rainfall to infest newly formed fruitlets
    
    Gate Requirements (ALL must be met):
    1. Orchard stage must be FRUITLET (post-flowering, young fruitlets forming)
    2. 24-hour accumulated rainfall must exceed threshold (soil moisture activation)
    3. Current timestep must show NO rainfall (emergence during drying period)
    4. Wind speed must be below threshold (weak fliers)
    5. Time must be crepuscular (dawn or dusk)
    
    If any condition fails, gate remains FULLY CLOSED.
    """

    REQUIRED_STAGE = OrchardStage.FRUITLET

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
        # 1. Stage check: MUST be in FRUITLET stage
        if orchard_stage != OrchardStage.FRUITLET:
            return False
        
        # 2. Rainfall accumulation check: need sufficient soil moisture
        if rainfall_history is not None:
            accumulated_rain = sum(rainfall_history)
            if accumulated_rain < CECID_RAINFALL_THRESHOLD_MM:
                return False
        else:
            # No history available, default closed for safety
            return False
        
        # 3. Current rainfall check: must be dry (emergence during drying)
        if CECID_NO_CURRENT_RAIN and rainfall_mm > 0.0:
            return False
        
        # 4. Wind check: gate closes above threshold
        if wind_speed_ms > CECID_WIND_THRESHOLD_MS:
            return False
        
        # 5. Crepuscular behavior: dawn or dusk only
        is_crepuscular = (DAWN_START <= hour < DAWN_END) or (DUSK_START <= hour < DUSK_END)
        if not is_crepuscular:
            return False
        
        return True

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
    ) -> None:
        wind_factor = max(0.0, 1.0 - wind_speed_ms / (CECID_WIND_THRESHOLD_MS * 2))
        dispersal_factor = 0.5 + 0.5 * wind_factor
        rain_factor = 1.0
        if rainfall_history is not None:
            accumulated = sum(rainfall_history)
            rain_factor = min(1.5, 1.0 + (accumulated - CECID_RAINFALL_THRESHOLD_MM) / 20.0)
        for dr, dc, dist in CECID_OFFSETS:
            tr, tc = src_r + dr, src_c + dc
            if not (0 <= tr < grid.rows and 0 <= tc < grid.cols):
                continue
            if grid.state[tr, tc] in (CellState.EMPTY, CellState.INFESTED, CellState.DEAD):
                continue

            prob = CECID_BASE_DISPERSAL_PROB * (CECID_DISTANCE_DECAY ** (dist - 1))
            prob *= dispersal_factor * rain_factor

            grid.apply_dispersal_probability(tr, tc, prob)


# ═════════════════════════════════════════════
#  Fruit Fly Gate
# ═════════════════════════════════════════════
class FruitFlyGate(DispersalGate):
    """
    Bactrocera spp. – phenology-calibrated, maturity-driven dispersal.
    
    Based on 2022-2025 historical data:
    - Strong seasonal peaks aligned with fruit development (May-July)
    - Unmanaged orchards show significantly higher CPTD values
    - Activity correlates with fruit maturity (sugar content attraction)
    
    Gate Requirements (ALL must be met):
    1. Orchard stage must be MATURE (ripe fruit present)
    2. Daytime hours (08:00-17:00)
    3. Temperature above threshold (warm weather)
    
    Dispersal Probability Factors:
    - Sugar index: riper fruit = stronger attraction (multiplier)
    - Neighbor threat: external pressure from unmanaged orchards (additive)
    - Wind direction: downwind bias for dispersal
    - Temperature: warmer = more active
    - Distance decay: standard CA framework
    """

    REQUIRED_STAGE = OrchardStage.MATURE

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
        # 1. Stage check: MUST be in MATURE stage
        if orchard_stage != OrchardStage.MATURE:
            return False
        
        # 2. Daytime check
        is_daytime = FRUIT_FLY_DAY_START <= hour < FRUIT_FLY_DAY_END
        if not is_daytime:
            return False
        
        # 3. Temperature check
        warm_enough = temperature_c >= FRUIT_FLY_TEMP_THRESHOLD_C
        if not warm_enough:
            return False
        
        return True

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
        """Use the smaller of infected sources or susceptible targets."""
        if not self.is_open(
            hour, wind_speed_ms, temperature_c,
            rainfall_mm, rainfall_history, orchard_stage, sugar_index
        ):
            return

        susceptible = grid.susceptible_mask
        if not susceptible.any():
            return

        infested = grid.infested_mask
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
    ) -> None:
        temp_factor = min(1.5, (temperature_c - FRUIT_FLY_TEMP_THRESHOLD_C) / 10.0 + 1.0)
        sugar_factor = sugar_index / FRUIT_FLY_SUGAR_INDEX_MAX
        ripeness_factor = 0.5 + 1.0 * sugar_factor
        wind_neighbor_factor = grid.get_wind_neighbor_factor(wind_dir_deg)
        for dr, dc, dist, target_angle in FRUIT_FLY_OFFSETS:
            tr, tc = src_r + dr, src_c + dc
            if not (0 <= tr < grid.rows and 0 <= tc < grid.cols):
                continue
            if grid.state[tr, tc] in (CellState.EMPTY, CellState.INFESTED, CellState.DEAD):
                continue

            prob = FRUIT_FLY_BASE_DISPERSAL_PROB * (FRUIT_FLY_DISTANCE_DECAY ** (dist - 1))

            # Wind-direction bias: target_angle is precomputed for this offset.
            ang_diff = _angular_diff(wind_dir_deg, target_angle)

            # Boost when target is downwind (small angular difference)
            if ang_diff < 45:
                prob += FRUIT_FLY_WIND_BOOST * (1.0 - ang_diff / 45.0)

            # Temperature bonus (warmer -> more active)
            prob *= temp_factor

            # Sugar index factor: riper fruit = stronger attraction
            # Sugar index ranges from ~0.3 (just entering mature) to 1.0 (fully ripe)
            prob *= ripeness_factor  # ranges from 0.5x to 1.5x

            # Neighbor threat factor: amplified when wind blows FROM the
            # direction of the neighbouring orchard (pests carried inward).
            neighbor_threat = grid.get_neighbor_threat(tr, tc)
            if neighbor_threat > 0.0:
                threat_boost = neighbor_threat * NEIGHBOR_THREAT_WEIGHT * wind_neighbor_factor
                prob += threat_boost

            grid.apply_dispersal_probability(tr, tc, prob)

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
        temp_factor = min(1.5, (temperature_c - FRUIT_FLY_TEMP_THRESHOLD_C) / 10.0 + 1.0)
        sugar_factor = sugar_index / FRUIT_FLY_SUGAR_INDEX_MAX
        ripeness_factor = 0.5 + 1.0 * sugar_factor
        wind_neighbor_factor = grid.get_wind_neighbor_factor(wind_dir_deg)

        for dr, dc, dist, target_angle in FRUIT_FLY_OFFSETS:
            src_r, src_c = target_r - dr, target_c - dc
            if not (0 <= src_r < grid.rows and 0 <= src_c < grid.cols):
                continue
            if grid.state[src_r, src_c] != CellState.INFESTED:
                continue

            prob = FRUIT_FLY_BASE_DISPERSAL_PROB * (FRUIT_FLY_DISTANCE_DECAY ** (dist - 1))

            ang_diff = _angular_diff(wind_dir_deg, target_angle)
            if ang_diff < 45:
                prob += FRUIT_FLY_WIND_BOOST * (1.0 - ang_diff / 45.0)

            prob *= temp_factor
            prob *= ripeness_factor

            neighbor_threat = grid.get_neighbor_threat(target_r, target_c)
            if neighbor_threat > 0.0:
                threat_boost = neighbor_threat * NEIGHBOR_THREAT_WEIGHT * wind_neighbor_factor
                prob += threat_boost

            grid.apply_dispersal_probability(target_r, target_c, prob)
