"""
Integration tests — grid mode stability and tree_graph end-to-end
==================================================================
Confirms:
  1. grid mode output is stable across runs (backward-compat regression guard)
  2. tree_graph mode runs end-to-end on the same minimal GeoJSON
  3. Both modes return a SimulationResponse with the expected shape
  4. simulation_mode field is correctly set in metadata
  5. A/B comparison: both modes accept identical inputs and return comparable metrics
"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# ─────────────────────────────────────────────
# Shared minimal orchard GeoJSON (10 trees)
# ─────────────────────────────────────────────
_ORIGIN_LON = 122.4020
_ORIGIN_LAT = 10.7910

# 10 trees in a 2 × 5 grid, 10 m apart
_TREE_GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [
                    _ORIGIN_LON + col * 0.00009,  # ≈ 10 m east
                    _ORIGIN_LAT + row * 0.00009,  # ≈ 10 m north
                ],
            },
            "properties": {
                "Tree_ID": f"T{row * 5 + col + 1}",
                "Status": "Unbagged",
                "crown_radius_m": 2.5,
            },
        }
        for row in range(2)
        for col in range(5)
    ],
}

_BASE_REQUEST_KWARGS = dict(
    pest_type="fruitfly",
    orchard_geojson=_TREE_GEOJSON,
    hours=6,
    orchard_stage="mature",
    days_since_flowering=60,
    neighbor_threat=0.0,
    random_seed=42,
    risk_threshold=0.5,
)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def _run_sync(request_kwargs: dict):
    """Run a simulation synchronously and return the response dict."""
    import asyncio
    from api.services.simulation_service import SimulationService
    from api.models.schemas import SimulationRequest

    svc = SimulationService()
    req = SimulationRequest(**request_kwargs)
    return asyncio.get_event_loop().run_until_complete(
        svc.run_simulation(req, weather_data=None)
    )


# ═════════════════════════════════════════════
# 1. grid mode — stability
# ═════════════════════════════════════════════
class TestGridStability:

    def test_grid_returns_response(self):
        """grid mode must complete without error and return a SimulationResponse."""
        from api.models.schemas import SimulationResponse
        resp = _run_sync({**_BASE_REQUEST_KWARGS, "simulation_mode": "grid"})
        assert isinstance(resp, SimulationResponse)

    def test_grid_metadata_mode_field(self):
        """SimulationMetadata.simulation_mode must be 'grid'."""
        resp = _run_sync({**_BASE_REQUEST_KWARGS, "simulation_mode": "grid"})
        assert resp.metadata.simulation_mode == "grid"

    def test_grid_reproducible_seed(self):
        """Two grid runs with the same seed must produce identical n_infested."""
        r1 = _run_sync({**_BASE_REQUEST_KWARGS, "simulation_mode": "grid"})
        r2 = _run_sync({**_BASE_REQUEST_KWARGS, "simulation_mode": "grid"})
        assert r1.n_infested_final == r2.n_infested_final

    def test_grid_default_mode_backward_compat(self):
        """Omitting simulation_mode must behave exactly like mode='grid'."""
        from api.models.schemas import SimulationRequest
        req_kw = {k: v for k, v in _BASE_REQUEST_KWARGS.items()}
        # Do NOT pass simulation_mode — confirm default
        req = SimulationRequest(**req_kw)
        assert req.simulation_mode.value == "grid"

    def test_grid_risk_geojson_structure(self):
        """Final risk_geojson must be a FeatureCollection."""
        resp = _run_sync({**_BASE_REQUEST_KWARGS, "simulation_mode": "grid"})
        rg = resp.risk_geojson
        assert rg["type"] == "FeatureCollection"
        assert isinstance(rg["features"], list)
        assert len(rg["features"]) > 0

    def test_grid_time_series_nonempty(self):
        """time_series must contain at least one snapshot."""
        resp = _run_sync({**_BASE_REQUEST_KWARGS, "simulation_mode": "grid"})
        assert len(resp.time_series) > 0

    def test_grid_peak_risk_in_range(self):
        """peak_risk must be in [0, 1]."""
        resp = _run_sync({**_BASE_REQUEST_KWARGS, "simulation_mode": "grid"})
        assert 0.0 <= resp.peak_risk <= 1.0

    def test_grid_tg_fields_are_none(self):
        """tree_graph-specific metadata fields must be None in grid mode."""
        resp = _run_sync({**_BASE_REQUEST_KWARGS, "simulation_mode": "grid"})
        assert resp.metadata.tg_lambda0 is None
        assert resp.metadata.tg_n_trees is None


# ═════════════════════════════════════════════
# 2. tree_graph mode — end-to-end
# ═════════════════════════════════════════════
class TestTreeGraphEndToEnd:

    def test_tree_graph_returns_response(self):
        """tree_graph mode must complete without error."""
        from api.models.schemas import SimulationResponse
        resp = _run_sync({**_BASE_REQUEST_KWARGS, "simulation_mode": "tree_graph"})
        assert isinstance(resp, SimulationResponse)

    def test_tree_graph_metadata_mode_field(self):
        """SimulationMetadata.simulation_mode must be 'tree_graph'."""
        resp = _run_sync({**_BASE_REQUEST_KWARGS, "simulation_mode": "tree_graph"})
        assert resp.metadata.simulation_mode == "tree_graph"

    def test_tree_graph_metadata_tg_fields_populated(self):
        """tree_graph metadata fields must be set."""
        resp = _run_sync({**_BASE_REQUEST_KWARGS, "simulation_mode": "tree_graph"})
        assert resp.metadata.tg_n_trees == 10
        assert resp.metadata.tg_lambda0 is not None
        assert resp.metadata.tg_alpha is not None
        assert resp.metadata.tg_n_edges is not None

    def test_tree_graph_risk_geojson_is_points(self):
        """tree_graph risk_geojson features must be Point geometries."""
        resp = _run_sync({**_BASE_REQUEST_KWARGS, "simulation_mode": "tree_graph"})
        rg = resp.risk_geojson
        assert rg["type"] == "FeatureCollection"
        for feat in rg["features"]:
            assert feat["geometry"]["type"] == "Point"

    def test_tree_graph_feature_has_crown_radius(self):
        """Each output feature must carry a crown_radius_m property."""
        resp = _run_sync({**_BASE_REQUEST_KWARGS, "simulation_mode": "tree_graph"})
        for feat in resp.risk_geojson["features"]:
            assert "crown_radius_m" in feat["properties"]

    def test_tree_graph_risk_in_range(self):
        """All tree risk values must be in [0, 1]."""
        resp = _run_sync({**_BASE_REQUEST_KWARGS, "simulation_mode": "tree_graph"})
        for feat in resp.risk_geojson["features"]:
            r = feat["properties"]["risk"]
            assert 0.0 <= r <= 1.0, f"Out-of-range risk: {r}"

    def test_tree_graph_reproducible_seed(self):
        """Two tree_graph runs with the same seed must produce identical n_infested."""
        r1 = _run_sync({**_BASE_REQUEST_KWARGS, "simulation_mode": "tree_graph"})
        r2 = _run_sync({**_BASE_REQUEST_KWARGS, "simulation_mode": "tree_graph"})
        assert r1.n_infested_final == r2.n_infested_final

    def test_tree_graph_time_series_nonempty(self):
        """time_series must contain at least one snapshot."""
        resp = _run_sync({**_BASE_REQUEST_KWARGS, "simulation_mode": "tree_graph"})
        assert len(resp.time_series) > 0

    def test_tree_graph_custom_lambda0(self):
        """Overriding tg_lambda0 must be reflected in metadata."""
        resp = _run_sync({
            **_BASE_REQUEST_KWARGS,
            "simulation_mode": "tree_graph",
            "tg_lambda0": 0.5,
        })
        assert abs(resp.metadata.tg_lambda0 - 0.5) < 1e-9

    def test_tree_graph_initial_infestation_tree_ids(self):
        """Seeding by tree ID must result in that tree being infested."""
        resp = _run_sync({
            **_BASE_REQUEST_KWARGS,
            "simulation_mode": "tree_graph",
            "initial_infestation_tree_ids": ["T1"],
        })
        # T1 should appear as infested in the final GeoJSON
        infested_ids = {
            f["properties"]["tree_id"]
            for f in resp.risk_geojson["features"]
            if f["properties"]["state"] == "infested"
        }
        assert "T1" in infested_ids


# ═════════════════════════════════════════════
# 3. A/B comparison — same inputs, both modes
# ═════════════════════════════════════════════
class TestABComparison:

    def test_both_modes_accept_identical_request(self):
        """Both modes must accept exactly the same request without errors."""
        r_grid = _run_sync({**_BASE_REQUEST_KWARGS, "simulation_mode": "grid"})
        r_tg   = _run_sync({**_BASE_REQUEST_KWARGS, "simulation_mode": "tree_graph"})
        assert r_grid.status == "completed"
        assert r_tg.status   == "completed"

    def test_both_have_same_run_hours(self):
        """hours field must match the request in both modes."""
        r_grid = _run_sync({**_BASE_REQUEST_KWARGS, "simulation_mode": "grid"})
        r_tg   = _run_sync({**_BASE_REQUEST_KWARGS, "simulation_mode": "tree_graph"})
        assert r_grid.hours == _BASE_REQUEST_KWARGS["hours"]
        assert r_tg.hours   == _BASE_REQUEST_KWARGS["hours"]

    def test_both_report_peak_risk(self):
        """Both responses must include a numeric peak_risk in [0, 1]."""
        for mode in ("grid", "tree_graph"):
            resp = _run_sync({**_BASE_REQUEST_KWARGS, "simulation_mode": mode})
            assert 0.0 <= resp.peak_risk <= 1.0, f"{mode}: peak_risk out of range"

    def test_grid_cells_at_risk_matches_geojson(self):
        """grid cells_at_risk count must be consistent with risk_geojson."""
        resp = _run_sync({**_BASE_REQUEST_KWARGS, "simulation_mode": "grid"})
        threshold = resp.risk_threshold
        counted = sum(
            1
            for f in resp.risk_geojson["features"]
            if f["properties"]["risk"] > threshold
        )
        # Allow small discrepancy since risk_geojson uses final snapshot
        # and cells_at_risk uses last risk_series slice — they should be close
        assert abs(counted - resp.cells_at_risk) <= 2

    def test_both_modes_have_correct_seed_in_metadata(self):
        """random_seed in metadata must match the request value."""
        for mode in ("grid", "tree_graph"):
            resp = _run_sync({**_BASE_REQUEST_KWARGS, "simulation_mode": mode})
            assert resp.random_seed == _BASE_REQUEST_KWARGS["random_seed"]
