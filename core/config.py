"""
MangoPoint — Configuration & Constants
=======================================
Central configuration for the Cellular Automata simulation engine.
All tuneable parameters live here so the rest of the codebase stays clean.

Phenology-calibrated biological trigger system grounded in 2022-2025 orchard records.
Historical data shows:
  - Fruit fly (CPTD) peaks: May-July, higher in unmanaged orchards
  - Cecid fly emergence: episodic, March-June (dry-to-wet transition)
"""

from enum import IntEnum
import numpy as np

# ─────────────────────────────────────────────
# Cell States
# ─────────────────────────────────────────────
class CellState(IntEnum):
    """Possible states for each grid cell (tree)."""
    EMPTY           = 0   # No tree in this cell
    UNBAGGED        = 1   # Tree present, fruit not bagged  (susceptible)
    BAGGED          = 2   # Tree present, fruit bagged      (resistant barrier)
    INFESTED        = 3   # Tree already infested            (infectious source)
    # Advanced Tree Management states (non-destructive extension)
    DEAD            = 4   # Tree permanently removed from simulation logic
    HISTORY_INFECTED = 5  # Previously infected, more prone to future infestation
    SUSPECT         = 6   # Near external infected area, flagged for monitoring


# ─────────────────────────────────────────────
# Orchard Phenological Stages
# ─────────────────────────────────────────────
class OrchardStage(IntEnum):
    """
    Phenological growth stages of mango orchard.
    
    These stages determine which pest gates can activate:
    - Cecid Fly (Gall Midge): Only active during FRUITLET stage
    - Fruit Fly (Bactrocera): Only active during MATURE stage
    """
    DORMANT   = 0   # Vegetative rest period, no flowering or fruit
    FLOWERING = 1   # Active flowering, no fruit yet
    FRUITLET  = 2   # Post-flowering, young fruitlets forming (Cecid Fly vulnerable)
    MATURE    = 3   # Fruit maturing/ripening (Fruit Fly attractive)


# ─────────────────────────────────────────────
# Grid Geometry
# ─────────────────────────────────────────────
CELL_SIZE_M          = 5.0        # metres per cell edge
DEFAULT_GRID_ROWS    = 30         # default rows  (north–south)
DEFAULT_GRID_COLS    = 30         # default cols  (east–west)


# ─────────────────────────────────────────────
# Simulation Time
# ─────────────────────────────────────────────
TIMESTEP_HOURS       = 1          # simulation resolution (hours)
FORECAST_HOURS       = 48         # prediction horizon
N_TIMESTEPS          = FORECAST_HOURS // TIMESTEP_HOURS


# ─────────────────────────────────────────────
# Biological Thresholds
# ─────────────────────────────────────────────

# —— Cecid Fly (Mango Gall Midge) ——
# Biological calibration from 2022-2025 data: episodic emergence in March-June
CECID_WIND_THRESHOLD_MS    = 3.0      # m/s – gate closes above this
CECID_BASE_DISPERSAL_PROB  = 0.12     # base per-neighbour probability at 1-cell distance
CECID_DISTANCE_DECAY       = 0.6      # multiplicative decay per additional cell distance
CECID_MAX_RANGE_CELLS      = 3        # maximum dispersal range in cells

# Rainfall-triggered emergence parameters (larvae emerge from soil after rain)
CECID_RAINFALL_THRESHOLD_MM  = 5.0    # 24-hour accumulated rainfall must exceed this
CECID_RAIN_HISTORY_HOURS     = 24     # hours to accumulate rainfall
CECID_NO_CURRENT_RAIN        = True   # current timestep must be dry (emergence during drying period)

# Crepuscular windows (hour of day, 24-h format)
DAWN_START  = 5
DAWN_END    = 7
DUSK_START  = 17
DUSK_END    = 19

# —— Fruit Fly (Bactrocera spp.) ——
# Biological calibration from 2022-2025 data: peaks May-July with fruit maturity
FRUIT_FLY_TEMP_THRESHOLD_C   = 25.0   # °C – gate closes below this
FRUIT_FLY_BASE_DISPERSAL_PROB = 0.08  # base per-neighbour probability
FRUIT_FLY_WIND_BOOST         = 0.15   # added probability for downwind cells
FRUIT_FLY_DISTANCE_DECAY     = 0.5
FRUIT_FLY_MAX_RANGE_CELLS    = 4
FRUIT_FLY_DAY_START          = 8      # active window start
FRUIT_FLY_DAY_END            = 17     # active window end

# Sugar index parameters (fruit attractiveness increases with ripeness)
FRUIT_FLY_SUGAR_INDEX_START      = 0.3    # initial sugar index when entering MATURE stage
FRUIT_FLY_SUGAR_INDEX_GROWTH     = 0.02   # sugar index increase per day
FRUIT_FLY_SUGAR_INDEX_MAX        = 1.0    # maximum sugar index (fully ripe)
FRUIT_FLY_DEFAULT_DAYS_FLOWERING = 60     # default days since flowering for MATURE stage

# Neighbor threat parameters (external orchard pressure)
NEIGHBOR_THREAT_WEIGHT = 0.3   # multiplier for neighbor threat influence on dispersal


# ─────────────────────────────────────────────
# Bagging Effectiveness
# ─────────────────────────────────────────────
BAG_RESISTANCE = 0.95   # 95 % reduction in infestation probability


# ─────────────────────────────────────────────
# Wind-direction helpers
# ─────────────────────────────────────────────
# 8-connected neighbour offsets  (row, col)
NEIGHBOUR_OFFSETS = np.array([
    (-1, -1), (-1, 0), (-1,  1),
    ( 0, -1),          ( 0,  1),
    ( 1, -1), ( 1, 0), ( 1,  1),
])

# Corresponding compass angles (degrees, meteorological convention: 0=N, 90=E)
NEIGHBOUR_ANGLES = np.array([
    315, 0, 45,
    270,    90,
    225, 180, 135,
], dtype=float)


# ─────────────────────────────────────────────
# Decision Support — Management Recommendation Zones
# ─────────────────────────────────────────────
# Zone classification thresholds (configurable, not hardcoded in UI)
# Zone 1 (Green): risk < DECISION_ZONE_LOW_THRESHOLD  → "No Action Required"
# Zone 2 (Yellow/Orange): low ≤ risk < high           → "Monitor / Manual Inspection"
# Zone 3 (Red): risk ≥ DECISION_ZONE_HIGH_THRESHOLD   → "Critical: Spray / Bag Now"
DECISION_ZONE_LOW_THRESHOLD   = 0.30   # Below this → Zone 1 (Safe)
DECISION_ZONE_HIGH_THRESHOLD  = 0.70   # At or above this → Zone 3 (Critical)

# Economic parameters for loss prevention metrics (optional)
# Set to None to disable money-saved calculations
PESTICIDE_COST_PER_HECTARE    = 2500.0   # PHP per hectare (adjust to local costs)
CELL_AREA_HECTARES            = 0.0025   # Area per grid cell in hectares (5m × 5m = 25m² = 0.0025 ha)


# ─────────────────────────────────────────────
# Visualisation Defaults
# ─────────────────────────────────────────────
RISK_CMAP       = "YlOrRd"
STATE_COLORS    = {
    CellState.EMPTY:            "#f0f0f0",
    CellState.UNBAGGED:         "#66bb6a",
    CellState.BAGGED:           "#42a5f5",
    CellState.INFESTED:         "#ef5350",
    # Advanced Tree Management states
    CellState.DEAD:             "#424242",   # Dark grey - permanently removed
    CellState.HISTORY_INFECTED: "#ff9800",   # Orange - previously infected
    CellState.SUSPECT:          "#9c27b0",   # Purple - flagged for monitoring
}

# Decision Support Zone Colors
DECISION_ZONE_COLORS = {
    "zone_1": "#22c55e",   # Green - No Action Required (safe)
    "zone_2": "#f59e0b",   # Amber/Orange - Monitor / Manual Inspection
    "zone_3": "#dc2626",   # Red - Critical: Spray / Bag Now
}
