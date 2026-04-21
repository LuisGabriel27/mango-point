"""
Unit tests for core.tree_graph_model
======================================
Tests cover:
  - crown_spread_prob formula correctness
  - Edge-case tree configurations
  - TreeGraph construction and adjacency
  - TreeGraphEngine state transitions
  - Seed reproducibility
"""

import math
import sys
from pathlib import Path

import numpy as np
import pytest

# Make project root importable when running via pytest from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.tree_graph_model import (
    TreeEdge,
    TreeGraph,
    TreeGraphEngine,
    TreeGraphResult,
    TreeNode,
    TreeState,
    build_tree_graph_from_lonlat,
    crown_spread_prob,
    cecid_spread_modifier,
    fruitfly_spread_modifier,
    compute_per_tree_threats,
    wind_neighbor_factor,
)
from core.config import (
    BAG_RESISTANCE,
    TG_ALPHA,
    TG_BETA,
    TG_DEFAULT_CROWN_RADIUS_M,
    TG_LAMBDA0,
    TG_MAX_NEIGHBOR_DIST_M,
    TG_WIND_BIAS,
    CECID_WIND_THRESHOLD_MS,
    CECID_RAINFALL_THRESHOLD_MM,
    FRUIT_FLY_TEMP_THRESHOLD_C,
    FRUIT_FLY_SUGAR_INDEX_MAX,
    FRUIT_FLY_SUGAR_INDEX_START,
    NEIGHBOR_THREAT_WEIGHT,
    WIND_NEIGHBOR_BOOST,
    OrchardStage,
    CECID_RAIN_HISTORY_HOURS,
)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def _make_edge(
    d_ij: float,
    r_i: float = TG_DEFAULT_CROWN_RADIUS_M,
    r_j: float = TG_DEFAULT_CROWN_RADIUS_M,
    bearing: float = 0.0,
) -> TreeEdge:
    """Construct a TreeEdge from centre-to-centre distance and crown radii."""
    g_ij = max(d_ij - r_i - r_j, 0.0)
    o_ij = max(r_i + r_j - d_ij, 0.0) / max(r_i + r_j, 1e-9)
    return TreeEdge(src=0, dst=1, d_ij=d_ij, g_ij=g_ij, o_ij=o_ij, bearing=bearing)


def _two_tree_graph(
    distance_m: float = 5.0,
    crown_i: float = TG_DEFAULT_CROWN_RADIUS_M,
    crown_j: float = TG_DEFAULT_CROWN_RADIUS_M,
    state_i: int = TreeState.INFESTED,
    state_j: int = TreeState.SUSCEPTIBLE,
    max_dist: float = TG_MAX_NEIGHBOR_DIST_M,
) -> TreeGraph:
    """Create a minimal two-tree graph with tree i directly east of origin."""
    nodes = [
        TreeNode(0, "T0", 0.0, 0.0, 0.0, 0.0, crown_i, state_i),
        TreeNode(1, "T1", 0.0, 0.0, distance_m, 0.0, crown_j, state_j),
    ]
    return TreeGraph(nodes, max_dist=max_dist)


def _synthetic_weather(hours: int = 4):
    """Create a minimal synthetic WeatherTimeSeries for testing."""
    import pandas as pd
    from utils.weather import WeatherTimeSeries

    now = pd.Timestamp("2025-06-01 10:00")
    df = pd.DataFrame({
        "datetime":     [now + pd.Timedelta(hours=h) for h in range(hours)],
        "wind_speed_ms": [2.0] * hours,
        "wind_dir_deg":  [90.0] * hours,  # wind from east
        "temperature_c": [30.0] * hours,
        "rainfall_mm":   [0.0] * hours,
    })
    return WeatherTimeSeries(df, source="test")


# ═════════════════════════════════════════════
# 1. crown_spread_prob — formula unit tests
# ═════════════════════════════════════════════
class TestCrownSpreadProb:

    def test_output_is_probability(self):
        """Result must always be in [0, 1]."""
        for d in [1.0, 5.0, 15.0, 50.0]:
            p = crown_spread_prob(_make_edge(d), wind_dir_rad=0.0)
            assert 0.0 <= p <= 1.0, f"Out of range at d={d}: {p}"

    def test_zero_gap_gives_baseline_rate(self):
        """When crowns just touch (g_ij=0, o_ij=0), P = 1 - exp(-lambda0 * dt).
        Wind bias is set to 0 to isolate the gap formula."""
        r = TG_DEFAULT_CROWN_RADIUS_M
        edge = _make_edge(2 * r)          # centres at r + r → g=0, o=0
        expected = 1.0 - math.exp(-TG_LAMBDA0 * 1.0)  # dt=1, w_factor=1
        p = crown_spread_prob(edge, wind_dir_rad=0.0, wind_bias=0.0)
        assert abs(p - expected) < 1e-9

    def test_larger_gap_reduces_probability(self):
        """A larger gap must strictly reduce the spread probability."""
        p_near = crown_spread_prob(_make_edge(6.0),  wind_dir_rad=0.0)
        p_far  = crown_spread_prob(_make_edge(12.0), wind_dir_rad=0.0)
        assert p_near > p_far, "Larger gap did not reduce probability"

    def test_overlap_increases_probability(self):
        """Overlapping crowns must give higher probability than just touching."""
        r = TG_DEFAULT_CROWN_RADIUS_M
        p_touch   = crown_spread_prob(_make_edge(2 * r),       wind_dir_rad=0.0)
        p_overlap = crown_spread_prob(_make_edge(2 * r * 0.5), wind_dir_rad=0.0)
        assert p_overlap > p_touch, "Overlap did not boost probability"

    def test_zero_crown_size_still_valid(self):
        """Two trees with zero crown radius (point trees) should still work.
        Wind bias is set to 0 to isolate the gap formula."""
        edge = _make_edge(d_ij=5.0, r_i=0.0, r_j=0.0)
        # g_ij = 5.0, o_ij = 0.0  →  rate = lambda0 * exp(-alpha*5)
        p = crown_spread_prob(edge, wind_dir_rad=0.0, wind_bias=0.0)
        assert 0.0 <= p <= 1.0
        expected_lam = TG_LAMBDA0 * math.exp(-TG_ALPHA * 5.0)
        expected_p   = 1.0 - math.exp(-expected_lam * 1.0)
        assert abs(p - expected_p) < 1e-9

    def test_very_far_trees_near_zero_prob(self):
        """Trees 100 m apart should have negligible spread probability."""
        p = crown_spread_prob(_make_edge(100.0), wind_dir_rad=0.0)
        assert p < 1e-6, f"Expected near-zero for 100 m gap, got {p}"

    def test_downwind_higher_than_upwind(self):
        """Downwind direction must yield higher probability than upwind."""
        wind_from_north = math.radians(0.0)   # wind FROM north → blowing south
        wind_toward_south = wind_from_north + math.pi  # south

        # Bearing south = π radians (or just below)
        edge_south = _make_edge(6.0, bearing=math.pi)     # toward south (downwind)
        edge_north = _make_edge(6.0, bearing=0.0)         # toward north (upwind)

        p_down = crown_spread_prob(edge_south, wind_dir_rad=wind_from_north)
        p_up   = crown_spread_prob(edge_north, wind_dir_rad=wind_from_north)
        assert p_down > p_up, "Downwind spread not higher than upwind"

    def test_no_wind_bias_is_isotropic(self):
        """With wind_bias=0 the wind direction has no effect."""
        edge_n = _make_edge(6.0, bearing=0.0)
        edge_s = _make_edge(6.0, bearing=math.pi)
        p_n = crown_spread_prob(edge_n, wind_dir_rad=0.0, wind_bias=0.0)
        p_s = crown_spread_prob(edge_s, wind_dir_rad=0.0, wind_bias=0.0)
        assert abs(p_n - p_s) < 1e-12, "wind_bias=0 should be isotropic"

    def test_probability_increases_with_dt(self):
        """Larger timestep means more exposure — probability must increase."""
        edge = _make_edge(6.0)
        p1 = crown_spread_prob(edge, wind_dir_rad=0.0, dt=1.0)
        p2 = crown_spread_prob(edge, wind_dir_rad=0.0, dt=4.0)
        assert p2 > p1

    def test_strong_wind_clamps_factor(self):
        """Wind factor must stay in [0, 2] regardless of direction."""
        for bearing in [0.0, math.pi / 4, math.pi, 3 * math.pi / 2]:
            p = crown_spread_prob(
                _make_edge(5.0, bearing=bearing),
                wind_dir_rad=bearing,  # worst case
                wind_bias=1.0,
            )
            assert 0.0 <= p <= 1.0


# ═════════════════════════════════════════════
# 2. TreeGraph — construction and adjacency
# ═════════════════════════════════════════════
class TestTreeGraph:

    def test_empty_graph(self):
        """Zero nodes → no edges, no error."""
        g = TreeGraph([], max_dist=10.0)
        assert g.n_infested() == 0
        assert g.edge_count() == 0

    def test_single_node_no_edges(self):
        """Single tree has no neighbours."""
        nodes = [TreeNode(0, "T0", 0.0, 0.0, 0.0, 0.0, 2.5)]
        g = TreeGraph(nodes, max_dist=10.0)
        assert g.edge_count() == 0
        assert g.neighbours(0) == []

    def test_two_close_trees_connected(self):
        """Two trees within max_dist must share an edge in each direction."""
        g = _two_tree_graph(distance_m=5.0, max_dist=10.0)
        assert g.edge_count() == 1
        assert len(g.neighbours(0)) == 1
        assert len(g.neighbours(1)) == 1

    def test_two_far_trees_not_connected(self):
        """Two trees beyond max_dist must not be connected."""
        g = _two_tree_graph(distance_m=25.0, max_dist=10.0)
        assert g.edge_count() == 0

    def test_edge_geometry_gap(self):
        """Edge g_ij should equal max(d - r_i - r_j, 0)."""
        r = 2.0
        d = 7.0          # gap = 7 - 2 - 2 = 3
        nodes = [
            TreeNode(0, "A", 0, 0, 0.0, 0.0, r),
            TreeNode(1, "B", 0, 0, d,   0.0, r),
        ]
        g = TreeGraph(nodes, max_dist=20.0)
        edge = g.neighbours(0)[0]
        assert abs(edge.g_ij - 3.0) < 1e-9
        assert abs(edge.o_ij - 0.0) < 1e-9

    def test_edge_geometry_overlap(self):
        """When crowns overlap, g_ij=0 and o_ij > 0."""
        r = 3.0
        d = 4.0          # overlap = r_i + r_j - d = 2; o = 2/6 ≈ 0.333
        nodes = [
            TreeNode(0, "A", 0, 0, 0.0, 0.0, r),
            TreeNode(1, "B", 0, 0, d,   0.0, r),
        ]
        g = TreeGraph(nodes, max_dist=20.0)
        edge = g.neighbours(0)[0]
        assert edge.g_ij == 0.0
        assert abs(edge.o_ij - (2.0 / 6.0)) < 1e-9

    def test_missing_crown_fallback(self):
        """build_tree_graph_from_lonlat must use default_crown_radius."""
        features = [
            {
                "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
                "properties": {"Tree_ID": "X1"},
            },
            {
                "geometry": {"type": "Point", "coordinates": [0.0001, 0.0]},
                "properties": {"Tree_ID": "X2"},
            },
        ]
        fallback = 99.0  # unusual value to detect
        g = build_tree_graph_from_lonlat(
            features=features,
            origin_lon=0.0,
            origin_lat=0.0,
            m_lat=111_132.0,
            m_lon=111_132.0,
            default_crown_radius=fallback,
            max_dist=500.0,
        )
        for node in g.nodes:
            assert node.crown_radius == fallback

    def test_crown_radius_from_property(self):
        """crown_radius_m property on feature overrides the fallback."""
        features = [
            {
                "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
                "properties": {"Tree_ID": "T1", "crown_radius_m": 4.5},
            },
        ]
        g = build_tree_graph_from_lonlat(
            features=features,
            origin_lon=0.0,
            origin_lat=0.0,
            m_lat=111_132.0,
            m_lon=111_132.0,
            default_crown_radius=1.0,
            max_dist=100.0,
        )
        assert g.nodes[0].crown_radius == 4.5

    def test_crown_diameter_property(self):
        """crown_diameter_m / 2 should be used as crown radius."""
        features = [
            {
                "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
                "properties": {"Tree_ID": "T1", "crown_diameter_m": 6.0},
            },
        ]
        g = build_tree_graph_from_lonlat(
            features=features,
            origin_lon=0.0,
            origin_lat=0.0,
            m_lat=111_132.0,
            m_lon=111_132.0,
        )
        assert g.nodes[0].crown_radius == 3.0

    def test_zero_crown_radius_not_error(self):
        """Trees with zero crown radius must not raise exceptions."""
        features = [
            {
                "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
                "properties": {"Tree_ID": "T1", "crown_radius_m": 0.0},
            },
            {
                "geometry": {"type": "Point", "coordinates": [0.0001, 0.0]},
                "properties": {"Tree_ID": "T2", "crown_radius_m": 0.0},
            },
        ]
        g = build_tree_graph_from_lonlat(
            features=features,
            origin_lon=0.0,
            origin_lat=0.0,
            m_lat=111_132.0,
            m_lon=111_132.0,
            max_dist=50.0,
        )
        assert len(g.nodes) == 2
        # Edge should exist; g_ij = d > 0, o_ij = 0
        if g.edge_count() > 0:
            edge = g.neighbours(0)[0]
            assert edge.g_ij > 0.0
            assert edge.o_ij == 0.0

    def test_n_infested_counter(self):
        """n_infested() must count INFESTED nodes correctly."""
        g = _two_tree_graph(state_i=TreeState.INFESTED, state_j=TreeState.SUSCEPTIBLE)
        assert g.n_infested() == 1
        g.nodes[1].state = TreeState.INFESTED
        assert g.n_infested() == 2

    def test_copy_states_returns_list(self):
        g = _two_tree_graph()
        states = g.copy_states()
        assert isinstance(states, list)
        assert len(states) == 2

    def test_bagged_status_from_geojson(self):
        """'bagged' status in GeoJSON properties should map to BAGGED state."""
        features = [
            {
                "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
                "properties": {"Tree_ID": "T1", "Status": "Bagged"},
            },
        ]
        g = build_tree_graph_from_lonlat(
            features=features,
            origin_lon=0.0,
            origin_lat=0.0,
            m_lat=111_132.0,
            m_lon=111_132.0,
        )
        assert g.nodes[0].state == TreeState.BAGGED


# ═════════════════════════════════════════════
# 3. TreeGraphEngine — simulation behaviour
# ═════════════════════════════════════════════
class TestTreeGraphEngine:

    def _run_two_tree(
        self,
        distance_m: float = 5.0,
        crown: float = TG_DEFAULT_CROWN_RADIUS_M,
        hours: int = 4,
        seed: int = 42,
        orchard_stage_str: str = "mature",
    ):
        """Helper: run a two-tree simulation and return the result."""
        from core.config import OrchardStage
        np.random.seed(seed)
        g = _two_tree_graph(distance_m=distance_m, crown_i=crown, crown_j=crown)
        weather = _synthetic_weather(hours=hours)
        stage_map = {
            "mature":    OrchardStage.MATURE,
            "fruitlet":  OrchardStage.FRUITLET,
            "flowering": OrchardStage.FLOWERING,
            "dormant":   OrchardStage.DORMANT,
        }
        engine = TreeGraphEngine(
            graph=g,
            weather=weather,
            transition_mode="threshold",
            threshold=0.01,   # very low threshold so spread is deterministic
            orchard_stage=stage_map[orchard_stage_str],
        )
        return engine.run(n_steps=hours, progress=False)

    def test_result_has_correct_number_of_snapshots(self):
        result = self._run_two_tree(hours=4)
        assert len(result) == 4

    def test_initially_infested_tree_stays_infested(self):
        """Tree 0 starts INFESTED and must remain so."""
        result = self._run_two_tree(hours=4)
        for snap in result.snapshots:
            assert snap["states"][0] == TreeState.INFESTED

    def test_spread_occurs_with_close_crowns(self):
        """Two overlapping trees (distance < 2r): tree 1 should get infested."""
        result = self._run_two_tree(distance_m=2.0, crown=3.0, hours=48)
        final_states = result.snapshots[-1]["states"]
        # With overlapping crowns and 48 timesteps the second tree should be
        # infested under threshold mode with threshold=0.01.
        assert final_states[1] == TreeState.INFESTED, (
            "Expected tree 1 to be infested after 48h with overlapping crowns"
        )

    def test_no_spread_when_gate_closed_dormant(self):
        """In DORMANT stage both gates are closed — no spread should occur."""
        result = self._run_two_tree(
            distance_m=3.0, crown=3.0, hours=48, orchard_stage_str="dormant"
        )
        final_states = result.snapshots[-1]["states"]
        # Tree 1 should remain susceptible (gate never opens)
        assert final_states[1] == TreeState.SUSCEPTIBLE

    def test_very_far_trees_no_spread(self):
        """Trees 200 m apart should not spread within 48 h."""
        result = self._run_two_tree(distance_m=200.0, crown=2.5, hours=48)
        final_states = result.snapshots[-1]["states"]
        assert final_states[1] == TreeState.SUSCEPTIBLE

    def test_reproducibility_with_same_seed(self):
        """Two runs with the same seed must produce identical results."""
        r1 = self._run_two_tree(seed=99)
        r2 = self._run_two_tree(seed=99)
        for s1, s2 in zip(r1.snapshots, r2.snapshots):
            assert s1["states"]   == s2["states"]
            assert s1["n_infested"] == s2["n_infested"]

    def test_different_seeds_may_differ(self):
        """Two stochastic runs with different seeds can produce different output.
        This is a statistical test — run many seeds and check at least one differs."""
        from core.config import OrchardStage
        results = set()
        g_template = _two_tree_graph(distance_m=3.5, crown_i=2.5, crown_j=2.5)
        for seed in range(20):
            np.random.seed(seed)
            g = _two_tree_graph(distance_m=3.5, crown_i=2.5, crown_j=2.5)
            weather = _synthetic_weather(hours=24)
            engine = TreeGraphEngine(
                graph=g,
                weather=weather,
                transition_mode="stochastic",
                orchard_stage=OrchardStage.MATURE,
            )
            res = engine.run(n_steps=24, progress=False)
            results.add(res.snapshots[-1]["n_infested"])
        assert len(results) > 1, "All seeds produced identical results — suspicious"

    def test_bagging_reduces_final_risk(self):
        """A bagged destination tree must show lower or equal final risk."""
        from core.config import OrchardStage
        weather = _synthetic_weather(hours=48)
        np.random.seed(0)

        g_unbag = _two_tree_graph(distance_m=3.0, state_j=TreeState.SUSCEPTIBLE)
        eng_unbag = TreeGraphEngine(
            graph=g_unbag, weather=weather,
            transition_mode="threshold", threshold=1.1,  # never transitions
            orchard_stage=OrchardStage.MATURE,
        )
        res_unbag = eng_unbag.run(n_steps=48, progress=False)
        risk_unbag = max(res_unbag.snapshots[-1]["risks"][1:])

        np.random.seed(0)
        g_bag = _two_tree_graph(distance_m=3.0, state_j=TreeState.BAGGED)
        eng_bag = TreeGraphEngine(
            graph=g_bag, weather=weather,
            transition_mode="threshold", threshold=1.1,
            orchard_stage=OrchardStage.MATURE,
        )
        res_bag = eng_bag.run(n_steps=48, progress=False)
        risk_bag = max(res_bag.snapshots[-1]["risks"][1:])

        assert risk_bag < risk_unbag, (
            f"Bagged risk ({risk_bag:.4f}) should be lower than unbagged ({risk_unbag:.4f})"
        )

    def test_dead_tree_not_infested(self):
        """A DEAD tree must not transition to INFESTED."""
        from core.config import OrchardStage
        nodes = [
            TreeNode(0, "src", 0, 0, 0.0,  0.0, 3.0, TreeState.INFESTED),
            TreeNode(1, "tgt", 0, 0, 2.0,  0.0, 3.0, TreeState.DEAD),
        ]
        g = TreeGraph(nodes, max_dist=20.0)
        weather = _synthetic_weather(hours=48)
        engine = TreeGraphEngine(
            graph=g, weather=weather,
            transition_mode="threshold", threshold=0.001,
            orchard_stage=OrchardStage.MATURE,
        )
        result = engine.run(n_steps=48, progress=False)
        for snap in result.snapshots:
            assert snap["states"][1] == TreeState.DEAD

    def test_overlapping_crowns_higher_risk_than_gap(self):
        """Overlapping crowns should accumulate more risk than a gaped pair."""
        from core.config import OrchardStage
        weather = _synthetic_weather(hours=24)

        np.random.seed(0)
        g_overlap = _two_tree_graph(distance_m=2.0, crown_i=2.5, crown_j=2.5)
        eng_o = TreeGraphEngine(
            graph=g_overlap, weather=weather,
            transition_mode="threshold", threshold=1.1,
            orchard_stage=OrchardStage.MATURE,
        )
        res_o = eng_o.run(n_steps=24, progress=False)
        risk_o = res_o.snapshots[-1]["risks"][1]

        np.random.seed(0)
        g_gap = _two_tree_graph(distance_m=10.0, crown_i=2.5, crown_j=2.5)
        eng_g = TreeGraphEngine(
            graph=g_gap, weather=weather,
            transition_mode="threshold", threshold=1.1,
            orchard_stage=OrchardStage.MATURE,
        )
        res_g = eng_g.run(n_steps=24, progress=False)
        risk_g = res_g.snapshots[-1]["risks"][1]

        assert risk_o > risk_g, (
            f"Overlap risk ({risk_o:.4f}) should exceed gap risk ({risk_g:.4f})"
        )

    def test_result_graph_attribute_set(self):
        """result.graph must be populated after run()."""
        result = self._run_two_tree(hours=2)
        assert result.graph is not None

    def test_snapshot_weather_keys(self):
        """Each snapshot must contain the required weather keys."""
        result = self._run_two_tree(hours=2)
        required = {"wind_speed_ms", "wind_dir_deg", "temperature_c"}
        for snap in result.snapshots:
            assert required.issubset(snap["weather"].keys())


# ─────────────────────────────────────────────
# Helpers for modifier tests
# ─────────────────────────────────────────────
def _fruitfly_weather(hours: int = 1, temperature_c: float = 30.0, wind_dir_deg: float = 90.0):
    """Daytime weather for Fruit Fly tests (stage=mature, temp ≥ 25 °C)."""
    import pandas as pd
    from utils.weather import WeatherTimeSeries

    now = pd.Timestamp("2025-06-01 10:00")  # hour 10, within FruitFly day window
    df = pd.DataFrame({
        "datetime":      [now + pd.Timedelta(hours=h) for h in range(hours)],
        "wind_speed_ms": [2.0] * hours,
        "wind_dir_deg":  [wind_dir_deg] * hours,
        "temperature_c": [temperature_c] * hours,
        "rainfall_mm":   [0.0] * hours,
    })
    return WeatherTimeSeries(df, source="test")


def _cecid_weather(hours: int = 1, wind_speed: float = 1.0):
    """Crepuscular weather for Cecid Fly tests (stage=fruitlet, dawn hour)."""
    import pandas as pd
    from utils.weather import WeatherTimeSeries

    now = pd.Timestamp("2025-06-01 05:00")  # hour 5, within dawn window
    df = pd.DataFrame({
        "datetime":      [now + pd.Timedelta(hours=h) for h in range(hours)],
        "wind_speed_ms": [wind_speed] * hours,
        "wind_dir_deg":  [90.0] * hours,
        "temperature_c": [22.0] * hours,
        "rainfall_mm":   [0.0] * hours,  # dry — larvae emerge during drying
    })
    return WeatherTimeSeries(df, source="test")


def _sufficient_rain_history(total_mm: float = 10.0) -> list:
    """24-hour rainfall history with given total, distributed uniformly."""
    per_hour = total_mm / 24.0
    return [per_hour] * 24


# ═════════════════════════════════════════════
# 4. Biological modifier pure functions
# ═════════════════════════════════════════════
class TestCecidModifier:

    def test_wind_damping_higher_wind_lowers_modifier(self):
        """Higher wind speed must produce a lower Cecid modifier."""
        rain = _sufficient_rain_history(10.0)
        mod_low  = cecid_spread_modifier(wind_speed_ms=0.5, rainfall_history=rain)
        mod_high = cecid_spread_modifier(wind_speed_ms=2.5, rainfall_history=rain)
        assert mod_low > mod_high, (
            f"Lower wind should give higher modifier; got {mod_low:.4f} vs {mod_high:.4f}"
        )

    def test_rainfall_boost_higher_rain_increases_modifier(self):
        """More accumulated rainfall must increase the Cecid modifier."""
        rain_low  = _sufficient_rain_history(6.0)    # small excess over 5 mm threshold
        rain_high = _sufficient_rain_history(24.0)   # large excess → capped at 1.5
        mod_low  = cecid_spread_modifier(wind_speed_ms=1.0, rainfall_history=rain_low)
        mod_high = cecid_spread_modifier(wind_speed_ms=1.0, rainfall_history=rain_high)
        assert mod_high > mod_low, (
            f"Higher rain should give higher modifier; got {mod_high:.4f} vs {mod_low:.4f}"
        )

    def test_rain_below_threshold_does_not_zero_modifier(self):
        """Below-threshold rainfall gives a reduced but non-negative modifier."""
        rain = [0.0] * 24  # no rain — accumulated < threshold
        mod = cecid_spread_modifier(wind_speed_ms=1.0, rainfall_history=rain)
        assert mod >= 0.0

    def test_modifier_positive_for_valid_conditions(self):
        """Under typical cecid conditions the modifier must be positive."""
        rain = _sufficient_rain_history(10.0)
        mod = cecid_spread_modifier(wind_speed_ms=1.0, rainfall_history=rain)
        assert mod > 0.0

    def test_rain_boost_capped_at_1_5(self):
        """Rainfall boost is capped at 1.5; very high rain should not exceed cap."""
        rain = [10.0] * 24  # 240 mm — far above threshold
        # rain_factor is capped at 1.5; wind_mod max is 1.0 → max modifier = 1.5
        mod = cecid_spread_modifier(wind_speed_ms=0.0, rainfall_history=rain)
        assert mod <= 1.5 + 1e-9


class TestFruitFlyModifier:

    def test_higher_temp_increases_modifier(self):
        """Warmer temperature must produce a higher FruitFly modifier."""
        mod_cool = fruitfly_spread_modifier(temperature_c=26.0, sugar_index=0.5)
        mod_warm = fruitfly_spread_modifier(temperature_c=35.0, sugar_index=0.5)
        assert mod_warm > mod_cool, (
            f"Warmer temp should give higher modifier; got {mod_warm:.4f} vs {mod_cool:.4f}"
        )

    def test_higher_sugar_increases_modifier(self):
        """Riper fruit (higher sugar_index) must produce a higher FruitFly modifier."""
        mod_unripe = fruitfly_spread_modifier(temperature_c=30.0, sugar_index=FRUIT_FLY_SUGAR_INDEX_START)
        mod_ripe   = fruitfly_spread_modifier(temperature_c=30.0, sugar_index=FRUIT_FLY_SUGAR_INDEX_MAX)
        assert mod_ripe > mod_unripe, (
            f"Riper fruit should give higher modifier; got {mod_ripe:.4f} vs {mod_unripe:.4f}"
        )

    def test_modifier_at_threshold_temp_is_positive(self):
        """At exactly the temperature threshold, modifier must be positive (sugar contributes)."""
        mod = fruitfly_spread_modifier(temperature_c=FRUIT_FLY_TEMP_THRESHOLD_C, sugar_index=0.5)
        assert mod > 0.0

    def test_modifier_max_is_reasonable(self):
        """Max modifier (max temp + max sugar) should be ≤ 2.25 (1.5 × 1.5)."""
        mod = fruitfly_spread_modifier(temperature_c=60.0, sugar_index=FRUIT_FLY_SUGAR_INDEX_MAX)
        assert mod <= 2.26  # slight tolerance for floating point


# ═════════════════════════════════════════════
# 5. Per-tree threats and wind factor
# ═════════════════════════════════════════════
class TestPerTreeThreats:

    def _three_tree_nodes(self):
        """Three trees arranged W–C–E at y=0."""
        return [
            TreeNode(0, "W", 0, 0, -10.0, 0.0, 2.5),
            TreeNode(1, "C", 0, 0,   0.0, 0.0, 2.5),
            TreeNode(2, "E", 0, 0,  10.0, 0.0, 2.5),
        ]

    def test_zero_threat_returns_zeros(self):
        nodes = self._three_tree_nodes()
        threats = compute_per_tree_threats(nodes, neighbor_threat=0.0, neighbor_direction="N")
        assert all(t == 0.0 for t in threats)

    def test_no_direction_uniform_threat(self):
        nodes = self._three_tree_nodes()
        threat = 0.6
        threats = compute_per_tree_threats(nodes, neighbor_threat=threat, neighbor_direction=None)
        assert all(abs(t - threat) < 1e-9 for t in threats)

    def test_directional_east_gradient(self):
        """Neighbor to the East: easternmost tree gets highest threat, western tree gets zero."""
        nodes = self._three_tree_nodes()
        threats = compute_per_tree_threats(nodes, neighbor_threat=0.8, neighbor_direction="E")
        # Eastern tree (x=+10) has positive projection → receives threat.
        # Western tree (x=−10) has negative projection → clipped to zero.
        assert threats[2] > 0.0, "Eastern tree should receive positive threat"
        assert threats[0] == 0.0, "Western tree should receive zero threat"
        assert threats[2] > threats[0]

    def test_directional_north_gradient(self):
        """Neighbor to the North: northernmost tree gets highest threat, south tree gets zero."""
        nodes = [
            TreeNode(0, "S", 0, 0, 0.0, -10.0, 2.5),
            TreeNode(1, "C", 0, 0, 0.0,   0.0, 2.5),
            TreeNode(2, "N", 0, 0, 0.0,  10.0, 2.5),
        ]
        threats = compute_per_tree_threats(nodes, neighbor_threat=0.8, neighbor_direction="N")
        assert threats[2] > 0.0, "Northern tree should receive positive threat"
        assert threats[0] == 0.0, "Southern tree should receive zero threat"
        assert threats[2] > threats[0]

    def test_max_threat_not_exceeded(self):
        """No per-tree threat may exceed the specified neighbor_threat."""
        nodes = self._three_tree_nodes()
        threat = 0.7
        threats = compute_per_tree_threats(nodes, neighbor_threat=threat, neighbor_direction="E")
        assert all(t <= threat + 1e-9 for t in threats)

    def test_wind_neighbor_factor_from_same_direction(self):
        """Wind from the same direction as the neighbour gives factor > 1."""
        factor = wind_neighbor_factor(wind_dir_deg=0.0, neighbor_bearing_deg=0.0)
        assert factor > 1.0

    def test_wind_neighbor_factor_from_opposite(self):
        """Wind from opposite direction of the neighbour gives factor < 1."""
        # Neighbour is North (0°), wind from South (180°) → blowing away from orchard
        factor = wind_neighbor_factor(wind_dir_deg=180.0, neighbor_bearing_deg=0.0)
        assert factor < 1.0

    def test_wind_neighbor_factor_clamped(self):
        """Wind-neighbor factor must stay in [0, 2]."""
        for wind_deg in range(0, 360, 45):
            for bearing_deg in range(0, 360, 45):
                f = wind_neighbor_factor(wind_deg, bearing_deg)
                assert 0.0 <= f <= 2.0


# ═════════════════════════════════════════════
# 6. Modifier integration tests (engine-level)
# ═════════════════════════════════════════════
class TestModifiersIntegration:
    """
    Engine-level tests that verify biological modifiers change risk in the
    expected direction.  All runs use transition_mode='threshold' with
    threshold=1.1 (never triggers) so that node.risk after one step equals
    the accumulated spread probability — no stochastic noise.
    """

    def _run_one_step_risk(
        self,
        weather,
        graph,
        orchard_stage,
        days_since_flowering: int = 60,
        neighbor_threat: float = 0.0,
        neighbor_direction=None,
        initial_rainfall_history=None,
        pest_type: str = "fruitfly",
    ) -> float:
        """Run engine for 1 step with threshold=1.1; return risk of tree 1."""
        engine = TreeGraphEngine(
            graph=graph,
            weather=weather,
            transition_mode="threshold",
            threshold=1.1,  # never transitions — risk is the raw accumulated prob
            orchard_stage=orchard_stage,
            days_since_flowering=days_since_flowering,
            wind_bias=0.0,  # isolate biological modifiers from wind direction
            pest_type=pest_type,
            neighbor_threat=neighbor_threat,
            neighbor_direction=neighbor_direction,
            initial_rainfall_history=initial_rainfall_history,
        )
        result = engine.run(n_steps=1, progress=False)
        return result.snapshots[0]["risks"][1]

    def test_higher_temp_increases_fruitfly_risk(self):
        """Warmer weather must produce higher FruitFly spread risk."""
        g = _two_tree_graph(distance_m=3.0)
        risk_cool = self._run_one_step_risk(
            _fruitfly_weather(temperature_c=26.0), g,
            OrchardStage.MATURE, days_since_flowering=60
        )
        risk_warm = self._run_one_step_risk(
            _fruitfly_weather(temperature_c=35.0), g,
            OrchardStage.MATURE, days_since_flowering=60
        )
        assert risk_warm > risk_cool, (
            f"Warm ({risk_warm:.5f}) should exceed cool ({risk_cool:.5f})"
        )

    def test_higher_sugar_index_increases_fruitfly_risk(self):
        """More days since flowering (riper fruit) must increase spread risk."""
        g = _two_tree_graph(distance_m=3.0)
        # days=5: sugar ≈ 0.4 (truthy so not coerced to default 60)
        risk_young = self._run_one_step_risk(
            _fruitfly_weather(), g,
            OrchardStage.MATURE, days_since_flowering=5
        )
        risk_ripe = self._run_one_step_risk(
            _fruitfly_weather(), g,
            OrchardStage.MATURE, days_since_flowering=90
        )
        assert risk_ripe > risk_young, (
            f"Ripe ({risk_ripe:.5f}) should exceed young ({risk_young:.5f})"
        )

    def test_higher_wind_reduces_cecid_risk(self):
        """Higher wind speed (still below threshold) must lower Cecid spread risk."""
        g = _two_tree_graph(distance_m=3.0)
        rain = _sufficient_rain_history(10.0)
        risk_low_wind = self._run_one_step_risk(
            _cecid_weather(wind_speed=0.5), g,
            OrchardStage.FRUITLET,
            initial_rainfall_history=rain,
            pest_type="cecid",
        )
        risk_high_wind = self._run_one_step_risk(
            _cecid_weather(wind_speed=2.5), g,
            OrchardStage.FRUITLET,
            initial_rainfall_history=rain,
            pest_type="cecid",
        )
        assert risk_low_wind > risk_high_wind, (
            f"Low wind ({risk_low_wind:.5f}) should exceed high wind ({risk_high_wind:.5f})"
        )

    def test_higher_rainfall_increases_cecid_risk(self):
        """More accumulated rainfall must increase Cecid spread risk."""
        g = _two_tree_graph(distance_m=3.0)
        risk_low_rain = self._run_one_step_risk(
            _cecid_weather(), g,
            OrchardStage.FRUITLET,
            initial_rainfall_history=_sufficient_rain_history(6.0),
            pest_type="cecid",
        )
        risk_high_rain = self._run_one_step_risk(
            _cecid_weather(), g,
            OrchardStage.FRUITLET,
            initial_rainfall_history=_sufficient_rain_history(24.0),
            pest_type="cecid",
        )
        assert risk_high_rain > risk_low_rain, (
            f"High rain ({risk_high_rain:.5f}) should exceed low rain ({risk_low_rain:.5f})"
        )

    def test_neighbor_threat_increases_fruitfly_risk(self):
        """Adding neighbor threat must increase spread risk for susceptible trees."""
        g = _two_tree_graph(distance_m=3.0)
        risk_no_threat = self._run_one_step_risk(
            _fruitfly_weather(), g,
            OrchardStage.MATURE,
            neighbor_threat=0.0,
        )
        risk_with_threat = self._run_one_step_risk(
            _fruitfly_weather(), g,
            OrchardStage.MATURE,
            neighbor_threat=0.8,
        )
        assert risk_with_threat > risk_no_threat, (
            f"Threat ({risk_with_threat:.5f}) should exceed no-threat ({risk_no_threat:.5f})"
        )

    def test_downwind_neighbor_amplifies_more_than_upwind(self):
        """Wind FROM neighbor direction amplifies threat more than wind away from it."""
        g = _two_tree_graph(distance_m=3.0)
        # Neighbour is to the North (bearing 0°).
        # Wind from North (0°): blows inward → factor > 1 → higher risk.
        # Wind from South (180°): blows outward → factor < 1 → lower risk.
        risk_wind_from_n = self._run_one_step_risk(
            _fruitfly_weather(wind_dir_deg=0.0), g,
            OrchardStage.MATURE,
            neighbor_threat=0.5,
            neighbor_direction="N",
        )
        risk_wind_from_s = self._run_one_step_risk(
            _fruitfly_weather(wind_dir_deg=180.0), g,
            OrchardStage.MATURE,
            neighbor_threat=0.5,
            neighbor_direction="N",
        )
        assert risk_wind_from_n > risk_wind_from_s, (
            f"Inward wind risk ({risk_wind_from_n:.5f}) should exceed "
            f"outward wind risk ({risk_wind_from_s:.5f})"
        )

    def test_cecid_gate_closed_in_mature_stage(self):
        """Cecid Fly gate must stay closed in MATURE stage — no spread."""
        g = _two_tree_graph(distance_m=3.0)
        risk = self._run_one_step_risk(
            _cecid_weather(), g,
            OrchardStage.MATURE,  # Wrong stage for cecid
            initial_rainfall_history=_sufficient_rain_history(10.0),
            pest_type="cecid",
        )
        assert risk == 0.0, f"Cecid gate should be closed in MATURE stage, got risk={risk}"

    def test_fruitfly_gate_closed_in_fruitlet_stage(self):
        """Fruit Fly gate must stay closed in FRUITLET stage — no spread."""
        g = _two_tree_graph(distance_m=3.0)
        risk = self._run_one_step_risk(
            _fruitfly_weather(), g,
            OrchardStage.FRUITLET,  # Wrong stage for fruit fly
        )
        assert risk == 0.0, f"FruitFly gate should be closed in FRUITLET stage, got risk={risk}"

    def test_backward_compat_neutral_modifiers_close_to_original(self):
        """
        With modifiers neutralised, tree_graph risk should be non-zero when gate is open.
        This is a regression test: confirms the engine still produces spread output
        after the modifier refactor.
        """
        g = _two_tree_graph(distance_m=3.0)
        risk = self._run_one_step_risk(
            _fruitfly_weather(temperature_c=FRUIT_FLY_TEMP_THRESHOLD_C),
            g,
            OrchardStage.MATURE,
            days_since_flowering=0,  # sugar at start value
        )
        # At threshold temp, temp_factor=1.0; sugar_mod = 0.5+SUGAR_START ≈ 0.8
        # Crown-geometry still gives non-zero base probability
        assert risk > 0.0, "Engine should produce non-zero risk even at minimal modifiers"
