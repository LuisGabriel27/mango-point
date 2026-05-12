"""
MangoPoint — Tree Graph Simulation Engine
==========================================
Crown-aware, tree-to-tree pest spread model for thesis comparison with the
grid-based cellular automata baseline.

Mathematical Model
------------------
Spread between trees i and j is modelled as a continuous-time Markov process.
The per-timestep spread probability is derived from a hazard rate that combines
crown geometry and wind direction.

Symbol Table
~~~~~~~~~~~~
n           number of trees in the orchard
i, j        tree indices (0 ≤ i, j < n)
x_i, y_i    Cartesian coordinates of tree i in a local metric projection (m)
            x = east, y = north;  origin = SW corner of bounding box
d_ij        Euclidean distance between centres of trees i and j (m)
              d_ij = sqrt((x_i - x_j)² + (y_i - y_j)²)
r_i, r_j    crown radii of trees i and j (m);
              if not supplied in GeoJSON, TG_DEFAULT_CROWN_RADIUS_M is used
g_ij        effective crown gap between trees i and j (m)
              g_ij = max(d_ij - r_i - r_j, 0)
              g_ij = 0 when crowns touch or overlap
o_ij        normalised crown overlap fraction  [0, 1]
              o_ij = max(r_i + r_j - d_ij, 0) / max(r_i + r_j, ε)
              o_ij = 0 when crowns are separated; → 1 as centres converge
dt          simulation timestep (hours); equals TG_DT = TIMESTEP_HOURS
lambda0     base spread hazard rate at zero gap (hr⁻¹); env-var TG_LAMBDA0
alpha       gap-decay coefficient (m⁻¹); env-var TG_ALPHA
              rate halves every ln(2)/alpha ≈ 3.5 m of gap at default alpha=0.2
beta        overlap-bonus coefficient (dimensionless); env-var TG_BETA
              at full overlap (o_ij=1) the rate is lambda0 × (1 + beta)
wind_bias   directional wind amplification [0, 1]; env-var TG_WIND_BIAS
              0 = isotropic spread; 1 = maximum downwind amplification
phi_ij      bearing from tree i to tree j (radians, 0 = North, CW positive)
              phi_ij = atan2(x_j - x_i, y_j - y_i)
theta_w     meteorological wind-from direction converted to radians
              "wind toward" = theta_w + π   (direction the wind is blowing TO)
lambda_ij   effective hazard rate from infested i to susceptible j (hr⁻¹)
              lambda_ij = lambda0 × exp(−alpha × g_ij) × (1 + beta × o_ij)
W_ij        wind factor (clamped to [0, 2])
              W_ij = 1 + wind_bias × cos(phi_ij − (theta_w + π))
              W_ij > 1 when i → j is downwind; W_ij < 1 upwind
P_ij        per-timestep spread probability from i to j
              P_ij = 1 − exp(−lambda_ij × W_ij × dt)
P_ij_eff    effective probability after bagging:
              P_ij_eff = P_ij × (1 − BAG_RESISTANCE)  if tree j is bagged
risk_j      cumulative infestation risk of tree j (union of independent sources)
              risk_j ← 1 − (1 − risk_j) × (1 − P_ij_eff)
              (accumulated over all currently infested neighbours i of j)

Key Formulas (plain language)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
1. Crown gap  —  if crowns are separated the gap decays the hazard rate
   exponentially; overlapping crowns get a bonus multiplier (1 + beta × o_ij).
2. Hazard rate  —  proportional to the effective contact opportunity between
   the two crowns.  Zero gap ⟹ baseline rate lambda0.
3. Wind factor  —  cosine modulation: spread is amplified downwind and
   suppressed upwind.  Clamped so it never goes negative.
4. Probability  —  Poisson arrival: the hazard rate integrated over dt gives
   the Bernoulli probability of one or more spread events in the timestep.
5. Risk accumulation  —  same union formula used by the grid model, so both
   modes are directly comparable when starting from the same seed.

Assumptions and Limitations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- Crown shapes are approximated as circles of radius r (top-down projection).
  Non-circular crowns (e.g., elongated mango canopies) are not modelled.
- Only trees within TG_MAX_NEIGHBOR_DIST_M of each other are connected.
  Long-range dispersal (e.g., by adult fruit fly) is not captured by this
  mechanism alone; it is implicitly included via the biological gate using the
  same open/close logic as the grid model.
- All coordinates are in a local planar projection (metres from SW origin).
  The service layer converts lon/lat using the same m_lat/m_lon constants as
  the grid model, so both modes share the same coordinate system.
- Bagging reduces the effective spread probability by BAG_RESISTANCE (95 %),
  identical to the grid model.
- The biological gate (CecidFlyGate / FruitFlyGate) is shared with the grid
  model: the same weather conditions open and close the activity window.
  Only the spatial spread mechanism differs between modes.

Thesis Comparison Protocol
~~~~~~~~~~~~~~~~~~~~~~~~~~~
To compare grid vs. tree_graph under identical experimental conditions:

1. **Same initial conditions**
   - Same orchard GeoJSON (identical tree positions and crown radii).
   - Same `orchard_stage`, `days_since_flowering`, `neighbor_threat`.
   - Same `random_seed` so stochastic draws are comparable.
   - Same initial infested trees: for grid mode supply `initial_infestation`
     as row/col pairs; for tree_graph mode supply
     `initial_infestation_tree_ids` (tree IDs from GeoJSON properties).

2. **Same weather inputs**
   - Pass the same forecast weather list in `weather_data` to both requests,
     or omit to let both fall back to the same synthetic series generated
     from the same seed.

3. **Metrics to compare**
   ┌─────────────────────────────┬──────────────────────────────────┐
   │ Metric                      │ Field in SimulationResponse       │
   ├─────────────────────────────┼──────────────────────────────────┤
   │ Spread extent               │ n_infested_final                  │
   │ Peak risk                   │ peak_risk                         │
   │ Trees / cells above threshold│ cells_at_risk                   │
   │ Directionality              │ risk_geojson (spatial heatmap)    │
   │ Computational cost          │ metadata.duration_seconds         │
   │ Error vs field observations │ POST /evaluation/evaluate         │
   └─────────────────────────────┴──────────────────────────────────┘

4. **Expected differences**
   - tree_graph should show more realistic cluster spread along canopy-contact
     paths where crowns touch or overlap.
   - grid may over-spread in open gaps between rows where no trees exist.
   - tree_graph runtime scales with n_trees × avg_neighbours;
     grid scales with rows × cols (often larger than n_trees).
   - tree_graph explicitly honours crown isolation: isolated trees in gaps are
     harder to reach, which the grid model ignores.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from core.config import (
    BAG_RESISTANCE,
    CECID_RAIN_HISTORY_HOURS,
    CECID_RAINFALL_THRESHOLD_MM,
    CECID_WIND_THRESHOLD_MS,
    DIRECTION_BEARING_MAP,
    FRUIT_FLY_DEFAULT_DAYS_FLOWERING,
    FRUIT_FLY_SUGAR_INDEX_GROWTH,
    FRUIT_FLY_SUGAR_INDEX_MAX,
    FRUIT_FLY_SUGAR_INDEX_START,
    FRUIT_FLY_TEMP_THRESHOLD_C,
    N_TIMESTEPS,
    NEIGHBOR_THREAT_WEIGHT,
    OrchardStage,
    TG_ALPHA,
    TG_BETA,
    TG_DEFAULT_CROWN_RADIUS_M,
    TG_DT,
    TG_LAMBDA0,
    TG_MAX_NEIGHBOR_DIST_M,
    TG_WIND_BIAS,
    WIND_NEIGHBOR_BOOST,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Tree-level state  (mirrors grid CellState)
# ─────────────────────────────────────────────
class TreeState(IntEnum):
    """Per-tree state for tree_graph mode.  Mirrors CellState for grid mode."""
    SUSCEPTIBLE = 1   # Unbagged, not yet infested
    BAGGED      = 2   # Bagged fruit — reduced infection risk
    INFESTED    = 3   # Currently infested (infectious source)
    DEAD        = 4   # Removed from simulation


# ─────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────
@dataclass
class TreeNode:
    """Single tree in the graph.

    Attributes
    ----------
    index       : position in TreeGraph.nodes list
    tree_id     : original GIS identifier (matches GeoJSON Tree_ID property)
    lon, lat    : geographic coordinates (degrees, EPSG:4326)
    x, y        : local planar coordinates (metres east / north from SW origin)
    crown_radius: crown radius (m)
    state       : current TreeState
    risk        : per-timestep accumulated spread probability [0, 1]
    """
    index: int
    tree_id: str
    lon: float
    lat: float
    x: float
    y: float
    crown_radius: float
    state: int = TreeState.SUSCEPTIBLE
    risk: float = 0.0
    treatment_susceptibility_factor: float = 1.0
    treatment_source_factor: float = 1.0
    treatment_active: bool = False


@dataclass
class TreeEdge:
    """Pre-computed geometric relationship between two neighbouring trees.

    All values are constant for the life of a simulation run (only tree
    positions and crown radii change if you re-build the graph).

    Attributes
    ----------
    src, dst    : node indices in TreeGraph.nodes
    d_ij        : centre-to-centre Euclidean distance (m)
    g_ij        : effective crown gap = max(d_ij − r_i − r_j, 0) (m)
    o_ij        : normalised overlap fraction [0, 1]
    bearing     : compass bearing from src to dst (radians, 0=N, CW positive)
    """
    src: int
    dst: int
    d_ij: float
    g_ij: float
    o_ij: float
    bearing: float


# ─────────────────────────────────────────────
# Spatial graph
# ─────────────────────────────────────────────
class TreeGraph:
    """
    Spatial graph of orchard trees connected by crown-proximity edges.

    Parameters
    ----------
    nodes    : list of TreeNode objects (positions and crown radii already set)
    max_dist : maximum centre-to-centre distance for edge inclusion (m)
    """

    def __init__(
        self,
        nodes: List[TreeNode],
        max_dist: float = TG_MAX_NEIGHBOR_DIST_M,
    ) -> None:
        self.nodes = nodes
        self.max_dist = max_dist
        self._edges_from: Dict[int, List[TreeEdge]] = {
            i: [] for i in range(len(nodes))
        }
        self._build()

    # ── graph construction ───────────────────────────────────────
    def _build(self) -> None:
        """Build adjacency list. Uses scipy KDTree or a local spatial hash."""
        if not self.nodes:
            return

        coords = np.array([[n.x, n.y] for n in self.nodes])

        try:
            from scipy.spatial import KDTree  # type: ignore[import]
            kd = KDTree(coords)
            # query_pairs returns all (i, j) pairs with i < j within radius
            raw_pairs: np.ndarray = kd.query_pairs(
                r=self.max_dist, output_type="ndarray"
            )
        except ImportError:
            logger.debug(
                "scipy not available; using spatial-hash graph build fallback"
            )
            raw_pairs = self._spatial_hash_pairs(coords, self.max_dist)

        for i_raw, j_raw in raw_pairs:
            i, j = int(i_raw), int(j_raw)
            ni, nj = self.nodes[i], self.nodes[j]
            dx = nj.x - ni.x
            dy = nj.y - ni.y
            d_ij = math.sqrt(dx * dx + dy * dy)
            if d_ij < 1e-9:
                continue  # coincident trees — skip degenerate edge
            if d_ij > self.max_dist:
                continue  # defensive guard for alternate pair providers

            r_sum = ni.crown_radius + nj.crown_radius
            g_ij = max(d_ij - r_sum, 0.0)
            o_ij = max(r_sum - d_ij, 0.0) / max(r_sum, 1e-9)

            # bearing: atan2(east-component, north-component) → 0=N, CW
            brg_ij = math.atan2(dx, dy)
            brg_ji = math.atan2(-dx, -dy)

            self._edges_from[i].append(TreeEdge(i, j, d_ij, g_ij, o_ij, brg_ij))
            self._edges_from[j].append(TreeEdge(j, i, d_ij, g_ij, o_ij, brg_ji))

        n_edges = sum(len(v) for v in self._edges_from.values()) // 2
        logger.debug(
            "TreeGraph: %d nodes, %d edges (max_dist=%.1f m)",
            len(self.nodes), n_edges, self.max_dist,
        )

    @staticmethod
    def _spatial_hash_pairs(coords: np.ndarray, max_dist: float) -> np.ndarray:
        """
        Return candidate pairs within ``max_dist`` without requiring scipy.

        Points are bucketed into square cells whose side length equals the
        search radius. Any two points within the radius must be in the same or
        one of the eight adjacent buckets, so sparse orchards avoid the old
        all-pairs scan when scipy is unavailable.
        """
        if len(coords) < 2 or max_dist <= 0.0 or not math.isfinite(max_dist):
            return np.empty((0, 2), dtype=np.intp)

        cell_size = float(max_dist)
        max_dist_sq = max_dist * max_dist
        buckets: Dict[Tuple[int, int], List[int]] = {}
        cell_keys: Dict[int, Tuple[int, int]] = {}

        for idx, (x_raw, y_raw) in enumerate(coords):
            x, y = float(x_raw), float(y_raw)
            if not (math.isfinite(x) and math.isfinite(y)):
                continue

            key = (
                math.floor(x / cell_size),
                math.floor(y / cell_size),
            )
            buckets.setdefault(key, []).append(idx)
            cell_keys[idx] = key

        pairs: List[Tuple[int, int]] = []
        for a, key in cell_keys.items():
            ax, ay = float(coords[a, 0]), float(coords[a, 1])
            cell_x, cell_y = key

            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    neighbour_key = (cell_x + dx, cell_y + dy)
                    for b in buckets.get(neighbour_key, []):
                        if b <= a:
                            continue

                        bx, by = float(coords[b, 0]), float(coords[b, 1])
                        delta_x = bx - ax
                        delta_y = by - ay
                        dist_sq = delta_x * delta_x + delta_y * delta_y
                        if 0.0 < dist_sq <= max_dist_sq:
                            pairs.append((a, b))

        return np.array(pairs, dtype=np.intp) if pairs else np.empty((0, 2), dtype=np.intp)

    # ── queries ──────────────────────────────────────────────────
    def neighbours(self, idx: int) -> List[TreeEdge]:
        """Return all outgoing edges from node *idx*."""
        return self._edges_from[idx]

    def infested_indices(self) -> List[int]:
        return [n.index for n in self.nodes if n.state == TreeState.INFESTED]

    def n_infested(self) -> int:
        return sum(1 for n in self.nodes if n.state == TreeState.INFESTED)

    def copy_states(self) -> List[int]:
        return [n.state for n in self.nodes]

    def copy_risks(self) -> List[float]:
        return [n.risk for n in self.nodes]

    def edge_count(self) -> int:
        return sum(len(v) for v in self._edges_from.values()) // 2


# ─────────────────────────────────────────────
# Result container  (mirrors SimulationResult)
# ─────────────────────────────────────────────
class TreeGraphResult:
    """Time-series output of one TreeGraph simulation run."""

    def __init__(self) -> None:
        self.snapshots: List[Dict] = []
        self.graph: Optional[TreeGraph] = None

    def append(
        self,
        timestep: int,
        dt,
        hour: int,
        states: List[int],
        risks: List[float],
        weather: dict,
        n_infested: int,
        n_new: int,
    ) -> None:
        self.snapshots.append({
            "timestep":   timestep,
            "datetime":   dt,
            "hour":       hour,
            "states":     list(states),
            "risks":      list(risks),
            "weather":    weather.copy(),
            "n_infested": n_infested,
            "n_new":      n_new,
        })

    def __len__(self) -> int:
        return len(self.snapshots)


# ─────────────────────────────────────────────
# Core spread-probability formula (pure function)
# ─────────────────────────────────────────────
def crown_spread_prob(
    edge: TreeEdge,
    wind_dir_rad: float,
    lambda0: float = TG_LAMBDA0,
    alpha: float = TG_ALPHA,
    beta: float = TG_BETA,
    wind_bias: float = TG_WIND_BIAS,
    dt: float = TG_DT,
) -> float:
    """
    Per-timestep spread probability along one directed edge.

    Formula (see module docstring for full symbol definitions):
        lambda_ij = lambda0 * exp(−alpha * g_ij) * (1 + beta * o_ij)
        W_ij      = clip(1 + wind_bias * cos(phi_ij − (theta_w + π)), 0, 2)
        P_ij      = 1 − exp(−lambda_ij * W_ij * dt)

    Parameters
    ----------
    edge         : pre-computed edge geometry (g_ij, o_ij, bearing phi_ij)
    wind_dir_rad : meteorological wind-FROM direction (radians, 0 = N, CW)
    lambda0      : base hazard rate (hr⁻¹)
    alpha        : gap-decay coefficient (m⁻¹)
    beta         : overlap-bonus coefficient
    wind_bias    : directional amplification [0, 1]
    dt           : timestep duration (hours)

    Returns
    -------
    float
        Probability in [0, 1].
    """
    # Effective hazard rate
    lam_ij = lambda0 * math.exp(-alpha * edge.g_ij) * (1.0 + beta * edge.o_ij)

    # Wind factor:  boost when i→j is downwind (phi_ij ≈ wind_toward)
    # wind_toward = direction wind is blowing TO = wind_dir_rad + π
    wind_toward = wind_dir_rad + math.pi
    w_factor = 1.0 + wind_bias * math.cos(edge.bearing - wind_toward)
    w_factor = max(0.0, min(2.0, w_factor))  # clamp to avoid negative prob

    return max(0.0, min(1.0, 1.0 - math.exp(-lam_ij * w_factor * dt)))


# ─────────────────────────────────────────────
# Biological modifier pure functions
# (mirror the modifiers in biological_rules.py
#  so both modes use identical biological logic)
# ─────────────────────────────────────────────

def cecid_spread_modifier(
    wind_speed_ms: float,
    rainfall_history,
) -> float:
    """
    Combined Cecid Fly dispersal modifier (multiplicative factor on P_geom).

    Mirrors CecidFlyGate._spread_from() in biological_rules.py.

    Wind damping  — Cecid Fly are weak fliers; high wind suppresses spread.
        wind_factor = max(0, 1 − wind_speed / (CECID_WIND_THRESHOLD × 2))
        wind_mod    = 0.5 + 0.5 × wind_factor   ∈ [0.5, 1.0]

    Rainfall boost — more soil moisture = more larval emergence.
        accumulated = Σ rainfall_history
        rain_factor = min(1.5, 1 + (accumulated − THRESHOLD) / 20)

    Returns  wind_mod × rain_factor  (≥ 0).
    """
    wind_factor = max(0.0, 1.0 - wind_speed_ms / (CECID_WIND_THRESHOLD_MS * 2.0))
    wind_mod = 0.5 + 0.5 * wind_factor

    accumulated = sum(rainfall_history)
    rain_factor = max(0.0, min(1.5, 1.0 + (accumulated - CECID_RAINFALL_THRESHOLD_MM) / 20.0))

    return wind_mod * rain_factor


def fruitfly_spread_modifier(
    temperature_c: float,
    sugar_index: float,
) -> float:
    """
    Combined Fruit Fly dispersal modifier (multiplicative factor on P_geom).

    Mirrors FruitFlyGate._spread_from() in biological_rules.py.

    Temperature — warmer conditions → more active flight.
        temp_factor = min(1.5, (T − T_thresh) / 10 + 1)   ∈ [0, 1.5]

    Sugar index — riper fruit → stronger attraction.
        sugar_mod   = 0.5 + sugar_index / S_max            ∈ [0.5, 1.5]

    Returns  temp_factor × sugar_mod  (≥ 0, max ≈ 2.25).
    """
    temp_factor = min(1.5, max(0.0, (temperature_c - FRUIT_FLY_TEMP_THRESHOLD_C) / 10.0 + 1.0))
    sugar_factor = sugar_index / max(FRUIT_FLY_SUGAR_INDEX_MAX, 1e-9)
    sugar_mod = 0.5 + 1.0 * sugar_factor
    return temp_factor * sugar_mod


def compute_per_tree_threats(
    nodes: List["TreeNode"],
    neighbor_threat: float,
    neighbor_direction: Optional[str] = None,
) -> List[float]:
    """
    Per-tree neighbor threat levels (mirrors OrchardGrid.set_neighbor_threat_directional).

    When *neighbor_direction* is given, trees on the edge facing that direction
    receive the full *neighbor_threat*; opposite-edge trees receive zero.
    The gradient is a linear projection onto the compass direction unit vector.

    Parameters
    ----------
    nodes              : tree nodes (must have .x, .y in local metres, x=east, y=north)
    neighbor_threat    : maximum threat level [0, 1]
    neighbor_direction : one of N, NE, E, SE, S, SW, W, NW — None for uniform

    Returns
    -------
    List[float] same length as nodes.
    """
    if neighbor_threat <= 0.0 or not nodes:
        return [0.0] * len(nodes)

    if not neighbor_direction:
        return [float(neighbor_threat)] * len(nodes)

    bearing_deg = DIRECTION_BEARING_MAP.get(neighbor_direction.upper(), 0.0)
    bearing_rad = math.radians(bearing_deg)
    # Direction unit vector in local Cartesian (x=east, y=north)
    u_x = math.sin(bearing_rad)
    u_y = math.cos(bearing_rad)

    xs = [n.x for n in nodes]
    ys = [n.y for n in nodes]
    cx = (max(xs) + min(xs)) / 2.0
    cy = (max(ys) + min(ys)) / 2.0

    projs = [(n.x - cx) * u_x + (n.y - cy) * u_y for n in nodes]
    max_proj = max(projs) if projs else 1.0

    if max_proj < 1e-9:
        return [float(neighbor_threat)] * len(nodes)

    return [
        float(max(0.0, min(neighbor_threat, neighbor_threat * p / max_proj)))
        for p in projs
    ]


def wind_neighbor_factor(wind_dir_deg: float, neighbor_bearing_deg: float) -> float:
    """
    Wind amplification factor for neighbor threat.

    When wind blows FROM the same direction as the neighbour, pests are
    carried inward → factor > 1.  Blowing away from the neighbour → factor < 1.

        factor = clip(1 + WIND_NEIGHBOR_BOOST × cos(wind_rad − bearing_rad), 0, 2)

    Mirrors OrchardGrid.get_wind_neighbor_factor() for tree_graph mode.
    """
    wind_rad    = math.radians(wind_dir_deg)
    bearing_rad = math.radians(neighbor_bearing_deg)
    return max(0.0, min(2.0, 1.0 + WIND_NEIGHBOR_BOOST * math.cos(wind_rad - bearing_rad)))


# ─────────────────────────────────────────────
# Simulation engine
# ─────────────────────────────────────────────
class TreeGraphEngine:
    """
    Tree-graph spread engine for pest dispersal simulation.

    Shares biological gating (CecidFlyGate / FruitFlyGate) with SimulationEngine
    but replaces the grid CA spatial model with crown-distance-based hazard rates.
    All biological triggers (phenology, rainfall, wind, temperature) are identical
    between modes, enabling clean A/B comparison.

    Parameters
    ----------
    graph               : TreeGraph with nodes and pre-built edges
    weather             : hourly WeatherTimeSeries covering the forecast window
    transition_mode     : 'stochastic' (default) or 'threshold'
    threshold           : risk threshold for deterministic transition (default 0.5)
    gates               : list of DispersalGate instances (default: both gates)
    orchard_stage       : phenological stage controlling which gates can open
    days_since_flowering: for fruit-fly sugar index calculation
    lambda0             : override TG_LAMBDA0 for this run
    alpha               : override TG_ALPHA for this run
    beta                : override TG_BETA for this run
    wind_bias           : override TG_WIND_BIAS for this run
    """

    def __init__(
        self,
        graph: TreeGraph,
        weather,  # WeatherTimeSeries (avoid circular import at type-check time)
        transition_mode: str = "stochastic",
        threshold: float = 0.5,
        gates=None,
        orchard_stage: OrchardStage = OrchardStage.MATURE,
        days_since_flowering: Optional[int] = None,
        lambda0: float = TG_LAMBDA0,
        alpha: float = TG_ALPHA,
        beta: float = TG_BETA,
        wind_bias: float = TG_WIND_BIAS,
        pest_type: str = "fruitfly",
        neighbor_threat: float = 0.0,
        neighbor_direction: Optional[str] = None,
        initial_rainfall_history: Optional[List[float]] = None,
        stage_per_tree: Optional[List[OrchardStage]] = None,
    ) -> None:
        # Deep-copy node states so original graph is preserved
        from collections import deque

        copied_nodes = [
            TreeNode(
                index=n.index,
                tree_id=n.tree_id,
                lon=n.lon,
                lat=n.lat,
                x=n.x,
                y=n.y,
                crown_radius=n.crown_radius,
                state=n.state,
                risk=n.risk,
                treatment_susceptibility_factor=n.treatment_susceptibility_factor,
                treatment_source_factor=n.treatment_source_factor,
                treatment_active=n.treatment_active,
            )
            for n in graph.nodes
        ]
        self.graph = TreeGraph.__new__(TreeGraph)
        self.graph.nodes = copied_nodes
        self.graph.max_dist = graph.max_dist
        # Edges encode only geometry → safe to share (immutable after build)
        self.graph._edges_from = graph._edges_from

        self.weather = weather
        self.transition_mode = transition_mode
        self.threshold = threshold

        from core.biological_rules import CecidFlyGate, FruitFlyGate
        self.gates = gates or [CecidFlyGate(), FruitFlyGate()]
        self.orchard_stage = orchard_stage

        # Per-tree stage list (mixed phenology). When provided, each gate
        # filters source trees by its own REQUIRED_STAGE so dispersal only
        # originates from trees whose per-tree stage matches.
        if stage_per_tree is not None:
            if len(stage_per_tree) != len(self.graph.nodes):
                raise ValueError(
                    f"stage_per_tree length {len(stage_per_tree)} does not match "
                    f"graph node count {len(self.graph.nodes)}"
                )
            self.stage_per_tree: Optional[List[int]] = [int(s) for s in stage_per_tree]
        else:
            self.stage_per_tree = None

        days = days_since_flowering or FRUIT_FLY_DEFAULT_DAYS_FLOWERING
        self.sugar_index: float = min(
            FRUIT_FLY_SUGAR_INDEX_MAX,
            FRUIT_FLY_SUGAR_INDEX_START + days * FRUIT_FLY_SUGAR_INDEX_GROWTH,
        )

        self.rainfall_history: deque = deque(maxlen=CECID_RAIN_HISTORY_HOURS)
        if initial_rainfall_history:
            # Fill with zeros, then append provided history so the tail is the recent history
            seed = [0.0] * CECID_RAIN_HISTORY_HOURS + [float(r) for r in initial_rainfall_history]
            for r in seed[-CECID_RAIN_HISTORY_HOURS:]:
                self.rainfall_history.append(r)
        else:
            for _ in range(CECID_RAIN_HISTORY_HOURS):
                self.rainfall_history.append(0.0)

        self.lambda0 = lambda0
        self.alpha = alpha
        self.beta = beta
        self.wind_bias = wind_bias

        # ── pest identity and neighbor pressure ──────────────────
        self.pest_type: str = pest_type

        self.neighbor_bearing: Optional[float] = (
            DIRECTION_BEARING_MAP.get(neighbor_direction.upper())
            if neighbor_direction else None
        )

        # Per-tree threat gradient (mirrors grid's directional neighbor layer).
        # Computed once at init; spatial distribution depends on neighbor_direction.
        self.per_tree_threats: List[float] = compute_per_tree_threats(
            self.graph.nodes, neighbor_threat, neighbor_direction
        )

        logger.info(
            "TreeGraphEngine init: n_trees=%d, n_edges=%d, mode=%s, "
            "lambda0=%.3f, alpha=%.3f, beta=%.3f, wind_bias=%.3f",
            len(graph.nodes),
            graph.edge_count(),
            transition_mode,
            lambda0,
            alpha,
            beta,
            wind_bias,
        )

    # ── main loop ────────────────────────────────────────────────
    def run(
        self,
        n_steps: Optional[int] = None,
        progress: bool = False,
    ) -> TreeGraphResult:
        """
        Execute the tree-graph simulation for *n_steps* hourly timesteps.

        Returns
        -------
        TreeGraphResult
            Full time-series of per-tree states and risks.
        """
        if n_steps is None:
            n_steps = min(N_TIMESTEPS, len(self.weather))

        result = TreeGraphResult()
        # Running high-water mark per tree (mirrors SimulationEngine.max_risk)
        max_risks: List[float] = [0.0] * len(self.graph.nodes)

        for step in range(n_steps):
            w = self.weather.at(step)
            current_rain: float = w.get("rainfall_mm", 0.0)
            self.rainfall_history.append(current_rain)

            # Advance sugar index (same rate as SimulationEngine)
            self.sugar_index = min(
                FRUIT_FLY_SUGAR_INDEX_MAX,
                self.sugar_index + FRUIT_FLY_SUGAR_INDEX_GROWTH / 24.0,
            )

            wind_speed: float = w["wind_speed_ms"]
            wind_dir_rad: float = math.radians(w["wind_dir_deg"])
            temperature: float = w["temperature_c"]
            hour: int = w["hour"]

            # Per-gate spread — each open gate contributes independently.
            # Contributions accumulate onto node.risk via union-of-probabilities.
            # Each gate method applies its own biological modifiers (mirroring
            # biological_rules.py), so both modes use identical trigger logic.
            from core.biological_rules import CecidFlyGate, FruitFlyGate
            for gate in self.gates:
                # When per-tree stages are set, the stage slot of is_open becomes
                # a no-op (we feed it gate.REQUIRED_STAGE) so only environmental
                # triggers gate the step; per-tree stage filters source trees.
                stage_for_gate = (
                    gate.REQUIRED_STAGE
                    if self.stage_per_tree is not None and gate.REQUIRED_STAGE is not None
                    else self.orchard_stage
                )
                if not gate.is_open(
                    hour=hour,
                    wind_speed_ms=wind_speed,
                    temperature_c=temperature,
                    rainfall_mm=current_rain,
                    rainfall_history=self.rainfall_history,
                    orchard_stage=stage_for_gate,
                    sugar_index=self.sugar_index,
                ):
                    continue
                if isinstance(gate, CecidFlyGate):
                    self._spread_cecid(wind_speed, wind_dir_rad)
                elif isinstance(gate, FruitFlyGate):
                    self._spread_fruitfly(wind_dir_rad, temperature)
                else:
                    # Fallback for custom gates: geometry-only spread
                    self._accumulate_risks(wind_dir_rad)

            # State transitions
            n_new = self._transition()
            n_inf = self.graph.n_infested()

            # Update running max-risk (same high-water logic as grid engine)
            for i, node in enumerate(self.graph.nodes):
                if node.state == TreeState.INFESTED:
                    max_risks[i] = 1.0
                else:
                    max_risks[i] = max(max_risks[i], node.risk)

            result.append(
                timestep=step,
                dt=w["datetime"],
                hour=hour,
                states=self.graph.copy_states(),
                risks=list(max_risks),
                weather=w,
                n_infested=n_inf,
                n_new=n_new,
            )

            # Reset per-step risk accumulator
            for node in self.graph.nodes:
                node.risk = 0.0

        result.graph = self.graph
        return result

    # ── internal helpers ─────────────────────────────────────────
    def _accumulate_risks(
        self,
        wind_dir_rad: float,
    ) -> None:
        """
        Generic fallback: crown-geometry spread without pest-specific modifiers.
        Used for unrecognised gate types. Standard pests use _spread_cecid /
        _spread_fruitfly which add biological modifiers on top of P_geom.
        """
        for src_idx in self.graph.infested_indices():
            src = self.graph.nodes[src_idx]
            for edge in self.graph.neighbours(src_idx):
                dst = self.graph.nodes[edge.dst]
                if dst.state in (TreeState.INFESTED, TreeState.DEAD):
                    continue

                prob = crown_spread_prob(
                    edge,
                    wind_dir_rad,
                    lambda0=self.lambda0,
                    alpha=self.alpha,
                    beta=self.beta,
                    wind_bias=self.wind_bias,
                    dt=TG_DT,
                )

                if dst.state == TreeState.BAGGED:
                    prob *= 1.0 - BAG_RESISTANCE
                prob *= src.treatment_source_factor
                prob *= dst.treatment_susceptibility_factor
                prob = max(0.0, min(1.0, prob))

                # Union of independent probabilities (same as grid model)
                dst.risk = 1.0 - (1.0 - dst.risk) * (1.0 - prob)

    def _transition(self) -> int:
        """Perform state transitions; return number of newly infested trees."""
        n_new = 0
        for node in self.graph.nodes:
            if node.state not in (TreeState.SUSCEPTIBLE, TreeState.BAGGED):
                continue
            if node.risk <= 0.0:
                continue
            if self.transition_mode == "stochastic":
                if np.random.random() < node.risk:
                    node.state = TreeState.INFESTED
                    n_new += 1
            else:
                if node.risk >= self.threshold:
                    node.state = TreeState.INFESTED
                    n_new += 1
        return n_new

    def _spread_cecid(
        self,
        wind_speed_ms: float,
        wind_dir_rad: float,
    ) -> None:
        """
        Accumulate Cecid Fly spread with biological modifiers.

        Applies cecid_spread_modifier() (wind damping + rainfall boost) as a
        multiplicative factor on the crown-geometry base probability P_geom.

            P_effective = P_geom × M_cecid   (× (1−BAG_RESISTANCE) if bagged)

        Contributions from multiple infested sources combine via
        union-of-independent-probabilities on node.risk.
        """
        modifier = cecid_spread_modifier(wind_speed_ms, self.rainfall_history)
        required_stage_int = int(OrchardStage.FRUITLET)

        for src_idx in self.graph.infested_indices():
            src = self.graph.nodes[src_idx]
            # Per-tree phenology: only FRUITLET trees can emit Cecid Fly dispersal.
            if (
                self.stage_per_tree is not None
                and self.stage_per_tree[src_idx] != required_stage_int
            ):
                continue
            for edge in self.graph.neighbours(src_idx):
                dst = self.graph.nodes[edge.dst]
                if dst.state in (TreeState.INFESTED, TreeState.DEAD):
                    continue
                if (
                    self.stage_per_tree is not None
                    and self.stage_per_tree[edge.dst] != required_stage_int
                ):
                    continue

                prob = crown_spread_prob(
                    edge, wind_dir_rad,
                    lambda0=self.lambda0, alpha=self.alpha,
                    beta=self.beta, wind_bias=self.wind_bias, dt=TG_DT,
                ) * modifier

                if dst.state == TreeState.BAGGED:
                    prob *= 1.0 - BAG_RESISTANCE
                prob *= src.treatment_source_factor
                prob *= dst.treatment_susceptibility_factor

                prob = max(0.0, min(1.0, prob))
                dst.risk = 1.0 - (1.0 - dst.risk) * (1.0 - prob)

    def _spread_fruitfly(
        self,
        wind_dir_rad: float,
        temperature_c: float,
    ) -> None:
        """
        Accumulate Fruit Fly spread with biological modifiers.

        Applies fruitfly_spread_modifier() (temperature + sugar index) as a
        multiplicative factor, then adds a per-tree neighbor threat boost
        wind-amplified by the direction of the neighboring orchard.

            prob  = P_geom × M_fruitfly
            prob += t_j × NEIGHBOR_THREAT_WEIGHT × f_nbr   (if threat > 0)
            P_effective = prob × (1−BAG_RESISTANCE)   if bagged

        Contributions combine via union-of-independent-probabilities on node.risk.
        """
        modifier = fruitfly_spread_modifier(temperature_c, self.sugar_index)

        # Orchard-wide wind-neighbor amplification scalar
        wind_dir_deg = math.degrees(wind_dir_rad)
        w_nbr: float = (
            wind_neighbor_factor(wind_dir_deg, self.neighbor_bearing)
            if self.neighbor_bearing is not None
            else 1.0
        )

        required_stage_int = int(OrchardStage.MATURE)

        for src_idx in self.graph.infested_indices():
            src = self.graph.nodes[src_idx]
            # Per-tree phenology: only MATURE trees can emit Fruit Fly dispersal.
            if (
                self.stage_per_tree is not None
                and self.stage_per_tree[src_idx] != required_stage_int
            ):
                continue
            for edge in self.graph.neighbours(src_idx):
                dst = self.graph.nodes[edge.dst]
                if dst.state in (TreeState.INFESTED, TreeState.DEAD):
                    continue
                if (
                    self.stage_per_tree is not None
                    and self.stage_per_tree[edge.dst] != required_stage_int
                ):
                    continue

                prob = crown_spread_prob(
                    edge, wind_dir_rad,
                    lambda0=self.lambda0, alpha=self.alpha,
                    beta=self.beta, wind_bias=self.wind_bias, dt=TG_DT,
                ) * modifier
                prob *= src.treatment_source_factor

                # Additive neighbor threat boost (same formula as grid model)
                dst_threat = (
                    self.per_tree_threats[edge.dst]
                    if edge.dst < len(self.per_tree_threats)
                    else 0.0
                )
                if dst_threat > 0.0:
                    prob += dst_threat * NEIGHBOR_THREAT_WEIGHT * w_nbr

                if dst.state == TreeState.BAGGED:
                    prob *= 1.0 - BAG_RESISTANCE
                prob *= dst.treatment_susceptibility_factor

                prob = max(0.0, min(1.0, prob))
                dst.risk = 1.0 - (1.0 - dst.risk) * (1.0 - prob)


# ─────────────────────────────────────────────
# Utility: build graph from lon/lat coordinates
# ─────────────────────────────────────────────
def _first_numeric_property(props: Dict[str, Any], names: Tuple[str, ...]) -> Optional[float]:
    """Return the first present numeric property, ignoring blanks and invalid values."""
    for name in names:
        if name not in props:
            continue
        value = props[name]
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def build_tree_graph_from_lonlat(
    features: List[Dict],
    origin_lon: float,
    origin_lat: float,
    m_lat: float,
    m_lon: float,
    default_crown_radius: float = TG_DEFAULT_CROWN_RADIUS_M,
    max_dist: float = TG_MAX_NEIGHBOR_DIST_M,
    bagged_ids: Optional[List[str]] = None,
) -> TreeGraph:
    """
    Convert a list of GeoJSON Point features into a TreeGraph.

    Parameters
    ----------
    features            : list of GeoJSON feature dicts (geometry.type = 'Point')
    origin_lon/lat      : SW corner of bounding box (degrees)
    m_lat, m_lon        : metres-per-degree scale factors for the orchard centre
    default_crown_radius: fallback crown radius (m) when not in feature properties
    max_dist            : maximum edge distance (m)
    bagged_ids          : set of tree IDs to mark as BAGGED

    Crown radius resolution (in priority order):
        1. ``crown_radius_m`` / ``crown_radius`` explicit radius properties
        2. ``crown_diameter_m`` property ÷ 2
        3. ``Crown_Width`` / ``crown_size`` canopy width properties divided by 2
        4. *default_crown_radius* constant
    """
    bagged_set = set(bagged_ids or [])
    nodes: List[TreeNode] = []

    for feat in features:
        geom = feat.get("geometry", {})
        if geom.get("type") != "Point":
            continue

        lon, lat = geom["coordinates"][0], geom["coordinates"][1]
        x = (lon - origin_lon) * m_lon  # metres east
        y = (lat - origin_lat) * m_lat  # metres north

        props = feat.get("properties") or {}
        tree_id = str(
            props.get("Tree_ID")
            or props.get("tree_id")
            or props.get("fid")
            or len(nodes)
        )

        radius_value = _first_numeric_property(
            props,
            ("crown_radius_m", "crown_radius"),
        )
        width_value = _first_numeric_property(
            props,
            (
                "crown_diameter_m",
                "crown_diameter",
                "crown_width_m",
                "crown_width",
                "Crown_Width",
                "crown_size_m",
                "crown_size",
            ),
        )

        if radius_value is not None:
            crown_r = radius_value
        elif width_value is not None:
            crown_r = width_value / 2.0
        else:
            crown_r = default_crown_radius

        crown_r = max(crown_r, 0.0)  # zero crown radius is valid (point tree)

        # Initial state
        status_raw = str(props.get("Status", "")).lower()
        if status_raw in ("bagged",) or tree_id in bagged_set:
            state = TreeState.BAGGED
        elif status_raw in ("infected", "infested"):
            state = TreeState.INFESTED
        elif status_raw in ("dead",):
            state = TreeState.DEAD
        else:
            state = TreeState.SUSCEPTIBLE

        nodes.append(
            TreeNode(
                index=len(nodes),
                tree_id=tree_id,
                lon=lon,
                lat=lat,
                x=x,
                y=y,
                crown_radius=crown_r,
                state=state,
            )
        )

    return TreeGraph(nodes, max_dist=max_dist)
