"""Prevent fruit-damage transitions from creating same-forecast adult sources."""

import asyncio

import numpy as np
import pandas as pd
import pytest

from api.models.schemas import SimulationRequest
from api.services.simulation_service import SimulationService
from core.biological_rules import FruitFlyGate
from core.config import CellState, OrchardStage, SIMULATION_MODEL_VERSION
from core.grid import OrchardGrid
from core.simulation_engine import SimulationEngine
from core.tree_graph_model import TreeGraph, TreeGraphEngine, TreeNode, TreeState
from utils.weather import WeatherTimeSeries


def _weather(hours=3):
    return WeatherTimeSeries(pd.DataFrame({
        "datetime": pd.date_range("2026-04-01T12:00:00+08:00", periods=hours, freq="h"),
        "temperature_c": [28.0] * hours, "wind_speed_ms": [1.0] * hours,
        "wind_dir_deg": [270.0] * hours, "rainfall_mm": [0.0] * hours,
    }))


def _engine(mode, mixed=False, reservoir=0.0):
    gate = FruitFlyGate(base_dispersal_prob=1.0, distance_decay=1.0, wind_boost=0.0)
    common = dict(gates=[gate], orchard_stage=OrchardStage.MATURE,
                  transition_mode="threshold", threshold=0.01)
    if mode == "grid":
        grid = OrchardGrid(1, 7)
        for col in (0, 3, 6):
            grid.set_state(0, col, CellState.INFESTED if col == 0 else CellState.UNBAGGED)
        grid.fruitfly_reservoir_pressure[0, 3] = reservoir
        return SimulationEngine(grid, _weather(),
                                stage_grid=np.full((1, 7), int(OrchardStage.MATURE)) if mixed else None,
                                **common)
    nodes = [TreeNode(i, str(i), 122.58 + i * 0.00014, 10.585, i * 15.0, 0, 2.5,
                      TreeState.INFESTED if i == 0 else TreeState.SUSCEPTIBLE)
             for i in range(3)]
    nodes[1].fruitfly_reservoir_pressure = reservoir
    return TreeGraphEngine(TreeGraph(nodes, max_dist=16.0), _weather(),
                           stage_per_tree=[OrchardStage.MATURE] * 3 if mixed else None,
                           lambda0=1.0, alpha=0.0, wind_bias=0.0, **common)


@pytest.mark.parametrize("mode", ["grid", "tree_graph"])
@pytest.mark.parametrize("mixed", [False, True])
def test_new_fruit_infestation_cannot_relay_adult_pressure_to_a_remote_target(mode, mixed):
    engine = _engine(mode, mixed)
    result = engine.run(n_steps=3, progress=False)
    if mode == "grid":
        assert result.grid.state[0, 3] == CellState.INFESTED
        assert result.grid.state[0, 6] == CellState.UNBAGGED
        assert all(snapshot["risk"][0, 6] == 0 for snapshot in result.snapshots)
    else:
        assert engine.graph.nodes[1].state == TreeState.INFESTED
        assert engine.graph.nodes[2].state == TreeState.SUSCEPTIBLE
        assert all(snapshot["risks"][2] == 0 for snapshot in result.snapshots)


@pytest.mark.parametrize("mode", ["grid", "tree_graph"])
def test_reservoir_strength_is_not_promoted_when_its_fruit_becomes_infested(mode):
    engine = _engine(mode, reservoir=0.2)
    control = _engine(mode, reservoir=0.2)
    engine.threshold = control.threshold = 2.0
    if mode == "grid":
        engine.grid.state[0, 3] = CellState.INFESTED
        result = engine.run(n_steps=1, progress=False)
        reference = control.run(n_steps=1, progress=False)
        assert engine.grid.state[0, 3] == CellState.INFESTED
        assert engine.grid.fruitfly_adult_source_pressure[0, 3] == 0.2
        observed = result.snapshots[0]["risk"][0, 6]
        expected = reference.snapshots[0]["risk"][0, 6]
    else:
        engine.graph.nodes[1].state = TreeState.INFESTED
        result = engine.run(n_steps=1, progress=False)
        reference = control.run(n_steps=1, progress=False)
        assert engine.graph.nodes[1].state == TreeState.INFESTED
        assert engine.fruitfly_adult_source_pressures[1] == 0.2
        observed = result.snapshots[0]["risks"][2]
        expected = reference.snapshots[0]["risks"][2]
    assert 0.0 < observed < 1.0
    assert observed == pytest.approx(expected)


def test_grid_copy_does_not_share_frozen_source_pressure():
    grid = OrchardGrid(1, 2)
    grid.set_state(0, 0, CellState.INFESTED)
    grid.freeze_fruitfly_sources()
    copied = grid.copy()
    copied.fruitfly_adult_source_pressure[0, 0] = 0.0
    assert grid.fruitfly_adult_source_pressure[0, 0] == 1.0


def test_connectivity_separates_a_connected_component_from_direct_source_exposure():
    engine = _engine("tree_graph")
    topology = SimulationService._tree_graph_connectivity(engine.graph, [0, 1, 2], [0])
    assert topology["largest_eligible_component"] == 3
    assert topology["source_reachable_tree_count"] == 2


@pytest.mark.parametrize("mode", ["grid", "tree_graph"])
@pytest.mark.parametrize("pest,stage", [("fruitfly", "mature"), ("cecid", "fruitlet")])
def test_saved_result_contains_versioned_source_and_metric_explanations(mode, pest, stage):
    orchard = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [122.58 + i * 0.00005, 10.585]},
         "properties": {"Tree_ID": str(i), "Status": "infected" if i == 0 else "healthy"}}
        for i in range(3)
    ]}
    request = SimulationRequest(pest_type=pest, orchard_stage=stage, simulation_mode=mode,
                                orchard_geojson=orchard, hours=1, random_seed=42)
    weather = [{"datetime": "2026-04-01T12:00:00+08:00", "temperature_c": 28.0,
                "wind_speed_ms": 1.0, "wind_dir_deg": 270.0, "rainfall_mm": 0.0}]
    result = asyncio.run(SimulationService().run_simulation(request, weather_data=weather))
    saved = result.model_dump(mode="json")["metadata"]
    assert saved["model_version"] == SIMULATION_MODEL_VERSION
    explanation = saved["model_interpretation"]
    assert "not measured fruit damage" in explanation["output_measure"]
    if pest == "fruitfly":
        assert "neither creates adult sources" in explanation["source_rule"]
        assert "Individual adult relocation" in explanation["movement_rule"]
    else:
        assert "Fruit-attacking Cecid only" in explanation["source_rule"]
        assert "first eligible hour" in explanation["outside_pressure"]
