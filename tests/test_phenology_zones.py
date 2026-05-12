"""
Phenology zones — unit + integration tests
==========================================
Covers:
  1. Pure helpers in core.phenology_zones (deterministic mix, quadrant mapping,
     breakdown aggregators) — no engine code.
  2. Biological rule plumbing: REQUIRED_STAGE attrs and compute_dispersal_per_cell
     actually filter source cells by per-cell stage.
  3. End-to-end through the simulation service: sending quadrant_stages yields a
     mixed stage_breakdown in the response metadata, while omitting it preserves
     the scalar-stage behaviour.
"""

import sys
import math
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import OrchardStage, CellState
from core.phenology_zones import (
    DEFAULT_MIX,
    QUADRANT_LABELS,
    assign_stage_with_mix,
    assign_stages_for_grid,
    assign_stages_for_points,
    bbox_quadrant,
    coerce_stage,
    stage_breakdown,
    stage_breakdown_from_grid,
    uniform_stage_grid,
)


# ═════════════════════════════════════════════
# 1. Pure helpers
# ═════════════════════════════════════════════
class TestCoerceStage:

    def test_coerce_accepts_enum(self):
        assert coerce_stage(OrchardStage.FLOWERING) is OrchardStage.FLOWERING

    def test_coerce_accepts_int(self):
        assert coerce_stage(int(OrchardStage.MATURE)) is OrchardStage.MATURE

    def test_coerce_accepts_str_case_insensitive(self):
        assert coerce_stage("Fruitlet") is OrchardStage.FRUITLET
        assert coerce_stage("DORMANT") is OrchardStage.DORMANT

    def test_coerce_rejects_garbage(self):
        with pytest.raises(ValueError):
            coerce_stage("not-a-stage")


class TestBboxQuadrant:

    def test_four_corners(self):
        bbox = (0.0, 0.0, 10.0, 10.0)
        assert bbox_quadrant(2.0, 8.0, bbox) == "nw"
        assert bbox_quadrant(8.0, 8.0, bbox) == "ne"
        assert bbox_quadrant(2.0, 2.0, bbox) == "sw"
        assert bbox_quadrant(8.0, 2.0, bbox) == "se"

    def test_midpoint_tie_break_is_south_and_west(self):
        # Tie-breaks default to the SW quadrant for a point on the exact midpoint.
        bbox = (0.0, 0.0, 10.0, 10.0)
        assert bbox_quadrant(5.0, 5.0, bbox) == "sw"


class TestAssignStageWithMix:

    def test_pure_dominant_mix_always_returns_dominant(self):
        rng = np.random.default_rng(0)
        picks = [assign_stage_with_mix(OrchardStage.FLOWERING, rng, mix=(1.0, 0.0, 0.0))
                 for _ in range(50)]
        assert all(p is OrchardStage.FLOWERING for p in picks)

    def test_pure_opposite_mix_always_returns_opposite(self):
        # DORMANT's opposite in the cycle is FRUITLET.
        rng = np.random.default_rng(0)
        picks = [assign_stage_with_mix(OrchardStage.DORMANT, rng, mix=(0.0, 0.0, 1.0))
                 for _ in range(50)]
        assert all(p is OrchardStage.FRUITLET for p in picks)

    def test_adjacent_only_mix_never_returns_dominant_or_opposite(self):
        rng = np.random.default_rng(0)
        picks = [assign_stage_with_mix(OrchardStage.FLOWERING, rng, mix=(0.0, 1.0, 0.0))
                 for _ in range(200)]
        # FLOWERING adjacents are DORMANT and FRUITLET.
        assert all(p in (OrchardStage.DORMANT, OrchardStage.FRUITLET) for p in picks)
        assert OrchardStage.FLOWERING not in picks
        assert OrchardStage.MATURE not in picks

    def test_default_mix_is_dominated_by_dominant(self):
        rng = np.random.default_rng(42)
        dom = OrchardStage.MATURE
        picks = [assign_stage_with_mix(dom, rng) for _ in range(1000)]
        dom_frac = sum(1 for p in picks if p is dom) / len(picks)
        # Default mix has p_dominant = 0.7; 1k draws should land well within 10%.
        assert 0.60 <= dom_frac <= 0.80


class TestAssignStagesForGrid:

    def test_shape_and_dtype(self):
        grid = assign_stages_for_grid(6, 6, {"nw": "flowering", "ne": "fruitlet",
                                              "sw": "mature",    "se": "dormant"}, seed=0)
        assert grid.shape == (6, 6)
        assert grid.dtype == np.int32

    def test_quadrants_roughly_carry_their_dominant(self):
        # Large grid so per-quadrant counts stabilise around 70%.
        rows = cols = 40
        grid = assign_stages_for_grid(
            rows, cols,
            {"nw": "flowering", "ne": "fruitlet", "sw": "dormant", "se": "mature"},
            seed=7,
        )
        # Grid rows: row 0 is southern (see module docstring).
        nw = grid[rows // 2 :, : cols // 2]
        ne = grid[rows // 2 :, cols // 2 :]
        sw = grid[: rows // 2, : cols // 2]
        se = grid[: rows // 2, cols // 2 :]
        assert (nw == int(OrchardStage.FLOWERING)).mean() > 0.55
        assert (ne == int(OrchardStage.FRUITLET)).mean()  > 0.55
        assert (sw == int(OrchardStage.DORMANT)).mean()   > 0.55
        assert (se == int(OrchardStage.MATURE)).mean()    > 0.55

    def test_missing_quadrant_falls_back(self):
        # Only NW provided — the rest should fall back to the `fallback` arg.
        grid = assign_stages_for_grid(
            8, 8, {"nw": "flowering"}, seed=0, fallback=OrchardStage.MATURE,
        )
        # SE cell definitely falls back (opposite corner).
        # Use the dominant-only mix to make this deterministic.
        grid_pure = assign_stages_for_grid(
            8, 8, {"nw": "flowering"}, seed=0,
            mix=(1.0, 0.0, 0.0), fallback=OrchardStage.MATURE,
        )
        # SE quadrant in a pure-dominant mix must all be MATURE (the fallback).
        assert (grid_pure[:4, 4:] == int(OrchardStage.MATURE)).all()

    def test_reproducible_with_seed(self):
        a = assign_stages_for_grid(10, 10, {"nw": "flowering", "ne": "fruitlet",
                                             "sw": "mature",    "se": "dormant"}, seed=123)
        b = assign_stages_for_grid(10, 10, {"nw": "flowering", "ne": "fruitlet",
                                             "sw": "mature",    "se": "dormant"}, seed=123)
        np.testing.assert_array_equal(a, b)


class TestAssignStagesForPoints:

    def test_empty_coords_returns_empty(self):
        assert assign_stages_for_points([], {"nw": "flowering"}) == []

    def test_length_matches_input(self):
        coords = [(0.1, 0.1), (0.9, 0.9), (0.1, 0.9), (0.9, 0.1)]
        stages = assign_stages_for_points(
            coords,
            {"nw": "flowering", "ne": "fruitlet", "sw": "dormant", "se": "mature"},
            seed=0,
        )
        assert len(stages) == 4


class TestBreakdowns:

    def test_stage_breakdown_has_all_keys(self):
        counts = stage_breakdown([OrchardStage.MATURE, OrchardStage.MATURE])
        assert set(counts.keys()) == {"dormant", "flowering", "fruitlet", "mature"}
        assert counts["mature"] == 2
        assert counts["dormant"] == 0

    def test_stage_breakdown_from_grid_mask(self):
        grid = uniform_stage_grid(4, 4, OrchardStage.FLOWERING)
        mask = np.zeros((4, 4), dtype=bool)
        mask[0, 0] = True
        mask[0, 1] = True
        counts = stage_breakdown_from_grid(grid, mask=mask)
        # Only masked-in cells are counted.
        assert counts["flowering"] == 2
        assert counts["mature"] == 0


# ═════════════════════════════════════════════
# 2. Biological rule plumbing
# ═════════════════════════════════════════════
class TestRequiredStage:

    def test_gates_declare_required_stage(self):
        from core.biological_rules import CecidFlyGate, FruitFlyGate
        assert CecidFlyGate.REQUIRED_STAGE is OrchardStage.FRUITLET
        assert FruitFlyGate.REQUIRED_STAGE is OrchardStage.MATURE

    def test_compute_dispersal_per_cell_filters_by_stage(self):
        """
        A grid with a single infested source emits risk only when that
        source's per-cell stage matches the gate's REQUIRED_STAGE.
        """
        from core.grid import OrchardGrid
        from core.biological_rules import FruitFlyGate
        from collections import deque

        def _fresh_grid():
            g = OrchardGrid(rows=5, cols=5, cell_size_m=1.0)
            # All susceptible except one source tree.
            g.state[:, :] = int(CellState.UNBAGGED)
            g.state[2, 2] = int(CellState.INFESTED)
            return g

        gate = FruitFlyGate()

        # Case 1: source is MATURE → gate should emit risk onto neighbours.
        g_mature = _fresh_grid()
        stage_mature = np.full((5, 5), int(OrchardStage.MATURE), dtype=np.int32)
        gate.compute_dispersal_per_cell(
            g_mature,
            stage_grid=stage_mature,
            hour=12, wind_speed_ms=1.0, wind_dir_deg=0.0,
            temperature_c=30.0,
            rainfall_mm=0.0,
            rainfall_history=deque([0.0] * 24, maxlen=24),
            sugar_index=0.9,
        )
        mature_total = g_mature.risk.sum()

        # Case 2: same grid but source is FRUITLET — FruitFlyGate requires
        # MATURE, so no risk may be accumulated anywhere.
        g_fruitlet = _fresh_grid()
        stage_fruitlet = np.full((5, 5), int(OrchardStage.FRUITLET), dtype=np.int32)
        gate.compute_dispersal_per_cell(
            g_fruitlet,
            stage_grid=stage_fruitlet,
            hour=12, wind_speed_ms=1.0, wind_dir_deg=0.0,
            temperature_c=30.0,
            rainfall_mm=0.0,
            rainfall_history=deque([0.0] * 24, maxlen=24),
            sugar_index=0.9,
        )
        assert g_fruitlet.risk.sum() == 0.0
        assert mature_total > 0.0

    def test_compute_dispersal_per_cell_filters_target_stage(self):
        """
        With mixed phenology, non-matching target trees must not accumulate risk.
        Fruit Fly can move from a mature source only into mature targets.
        """
        from core.grid import OrchardGrid
        from core.biological_rules import FruitFlyGate
        from collections import deque

        g = OrchardGrid(rows=5, cols=5, cell_size_m=1.0)
        g.state[:, :] = int(CellState.EMPTY)
        g.state[2, 2] = int(CellState.INFESTED)
        g.state[2, 1] = int(CellState.UNBAGGED)
        g.state[2, 3] = int(CellState.UNBAGGED)

        stage_grid = np.full((5, 5), int(OrchardStage.DORMANT), dtype=np.int32)
        stage_grid[2, 2] = int(OrchardStage.MATURE)
        stage_grid[2, 3] = int(OrchardStage.MATURE)

        FruitFlyGate().compute_dispersal_per_cell(
            g,
            stage_grid=stage_grid,
            hour=12, wind_speed_ms=1.0, wind_dir_deg=0.0,
            temperature_c=30.0,
            rainfall_mm=0.0,
            rainfall_history=deque([0.0] * 24, maxlen=24),
            sugar_index=0.9,
        )

        assert g.risk[2, 1] == 0.0
        assert g.risk[2, 3] > 0.0

    def test_tree_graph_spread_filters_target_stage(self):
        from core.tree_graph_model import TreeGraph, TreeGraphEngine, TreeNode, TreeState
        from utils.weather import WeatherTimeSeries

        graph = TreeGraph(
            [
                TreeNode(0, "src", 0.0, 0.0, 0.0, 0.0, 3.0, TreeState.INFESTED),
                TreeNode(1, "dormant", 0.0, 0.0, 2.0, 0.0, 3.0, TreeState.SUSCEPTIBLE),
                TreeNode(2, "mature", 0.0, 0.0, -2.0, 0.0, 3.0, TreeState.SUSCEPTIBLE),
            ],
            max_dist=10.0,
        )
        engine = TreeGraphEngine(
            graph,
            weather=WeatherTimeSeries.synthetic(hours=1),
            stage_per_tree=[OrchardStage.MATURE, OrchardStage.DORMANT, OrchardStage.MATURE],
        )

        engine._spread_fruitfly(math.radians(0.0), temperature_c=30.0)

        assert engine.graph.nodes[1].risk == 0.0
        assert engine.graph.nodes[2].risk > 0.0


# ═════════════════════════════════════════════
# 3. End-to-end through the simulation service
# ═════════════════════════════════════════════
_ORIGIN_LON = 122.4020
_ORIGIN_LAT = 10.7910
_TREE_GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [
                    _ORIGIN_LON + col * 0.00009,
                    _ORIGIN_LAT + row * 0.00009,
                ],
            },
            "properties": {
                "Tree_ID": f"T{row * 5 + col + 1}",
                "Status": "Unbagged",
                "crown_radius_m": 2.5,
            },
        }
        for row in range(4)
        for col in range(4)
    ],
}

_BASE_REQUEST_KWARGS = dict(
    pest_type="fruitfly",
    orchard_geojson=_TREE_GEOJSON,
    hours=4,
    orchard_stage="mature",
    days_since_flowering=60,
    neighbor_threat=0.0,
    random_seed=42,
    risk_threshold=0.5,
)


def _run_sync(request_kwargs: dict):
    import asyncio
    from api.services.simulation_service import SimulationService
    from api.models.schemas import SimulationRequest

    svc = SimulationService()
    req = SimulationRequest(**request_kwargs)
    return asyncio.get_event_loop().run_until_complete(
        svc.run_simulation(req, weather_data=None)
    )


class TestServiceIntegration:

    def test_scalar_stage_keeps_single_slice_breakdown(self):
        resp = _run_sync({**_BASE_REQUEST_KWARGS, "simulation_mode": "grid"})
        # When no quadrant_stages is supplied, the breakdown must be a single
        # bucket equal to the scalar stage — matches the legacy donut behaviour.
        sb = resp.metadata.stage_breakdown
        assert sb is not None
        assert sum(sb.values()) > 0
        assert sb["mature"] == sum(sb.values())
        assert resp.metadata.quadrant_stages is None

    def test_quadrant_stages_produces_mixed_breakdown_grid(self):
        resp = _run_sync({
            **_BASE_REQUEST_KWARGS,
            "simulation_mode": "grid",
            "quadrant_stages": {
                "nw": "flowering",
                "ne": "fruitlet",
                "sw": "dormant",
                "se": "mature",
            },
        })
        sb = resp.metadata.stage_breakdown
        assert sb is not None
        # All four stages should have non-zero representation with 16 trees
        # and four different quadrant dominants (the 70/20/10 mix still lets
        # every stage appear somewhere).
        nonzero = [s for s, c in sb.items() if c > 0]
        assert len(nonzero) >= 2, f"expected mixed breakdown, got {sb}"
        assert resp.metadata.quadrant_stages == {
            "nw": "flowering", "ne": "fruitlet",
            "sw": "dormant",   "se": "mature",
        }

    def test_quadrant_stages_produces_mixed_breakdown_tree_graph(self):
        resp = _run_sync({
            **_BASE_REQUEST_KWARGS,
            "simulation_mode": "tree_graph",
            "quadrant_stages": {
                "nw": "flowering",
                "ne": "fruitlet",
                "sw": "dormant",
                "se": "mature",
            },
        })
        sb = resp.metadata.stage_breakdown
        assert sb is not None
        assert sum(sb.values()) == 16  # one entry per tree
        nonzero = [s for s, c in sb.items() if c > 0]
        assert len(nonzero) >= 2

    def test_quadrant_stages_is_reproducible_with_seed(self):
        kwargs = {
            **_BASE_REQUEST_KWARGS,
            "simulation_mode": "grid",
            "quadrant_stages": {
                "nw": "flowering", "ne": "fruitlet",
                "sw": "dormant",   "se": "mature",
            },
        }
        r1 = _run_sync(kwargs)
        r2 = _run_sync(kwargs)
        assert r1.metadata.stage_breakdown == r2.metadata.stage_breakdown

    def test_tree_stage_overrides_allow_grid_seed_in_matching_stage_zone(self):
        resp = _run_sync({
            **_BASE_REQUEST_KWARGS,
            "simulation_mode": "grid",
            "orchard_stage": "fruitlet",
            "tree_stage_overrides": {"T1": "mature"},
        })

        assert resp.metadata.tree_stage_override_count == 1
        assert resp.metadata.stage_breakdown["mature"] == 1
        assert resp.metadata.initial_seed_count == 1
        assert resp.metadata.initial_seed_strategy != "none_inactive_stage"

    def test_tree_stage_overrides_allow_tree_graph_seed_in_matching_stage_zone(self):
        resp = _run_sync({
            **_BASE_REQUEST_KWARGS,
            "simulation_mode": "tree_graph",
            "orchard_stage": "fruitlet",
            "tree_stage_overrides": {"T1": "mature"},
        })

        assert resp.metadata.tree_stage_override_count == 1
        assert resp.metadata.stage_breakdown["mature"] == 1
        assert resp.metadata.initial_seed_count == 1
        assert resp.metadata.initial_seed_strategy != "none_inactive_stage"
