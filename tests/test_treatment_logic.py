import asyncio
import math

import numpy as np
import pytest

from api.models.schemas import SimulationRequest
from api.services.simulation_service import SimulationService
from core.biological_rules import FruitFlyGate
from core.config import CellState
from core.grid import OrchardGrid
from core.tree_graph_model import TreeGraph, TreeGraphEngine, TreeNode, TreeState
from utils.weather import WeatherTimeSeries


def _grid_with_source_and_target():
    grid = OrchardGrid(rows=5, cols=5, cell_size_m=1.0)
    mask = np.zeros((5, 5), dtype=bool)
    mask[2, 2] = True
    mask[2, 3] = True
    grid.plant_trees(mask, CellState.UNBAGGED)
    grid.infest(2, 2)
    return grid


def test_grid_treatment_reduces_target_susceptibility():
    untreated = _grid_with_source_and_target()
    treated = _grid_with_source_and_target()
    target_mask = np.zeros((5, 5), dtype=bool)
    target_mask[2, 3] = True
    treated.apply_treatment_mask(target_mask, susceptibility_reduction=0.50)

    gate = FruitFlyGate()
    gate._spread_from(untreated, 2, 2, 1.0, 0.0, 30.0, sugar_index=0.5)
    gate._spread_from(treated, 2, 2, 1.0, 0.0, 30.0, sugar_index=0.5)

    assert treated.risk[2, 3] == pytest.approx(untreated.risk[2, 3] * 0.5)
    assert treated.treatment_active[2, 3]


def test_grid_treatment_reduces_infested_source_pressure():
    untreated = _grid_with_source_and_target()
    treated = _grid_with_source_and_target()
    source_mask = np.zeros((5, 5), dtype=bool)
    source_mask[2, 2] = True
    treated.apply_treatment_mask(
        source_mask,
        susceptibility_reduction=0.0,
        source_reduction=0.75,
    )

    gate = FruitFlyGate()
    gate._spread_from(untreated, 2, 2, 1.0, 0.0, 30.0, sugar_index=0.5)
    gate._spread_from(treated, 2, 2, 1.0, 0.0, 30.0, sugar_index=0.5)

    assert treated.risk[2, 3] == pytest.approx(untreated.risk[2, 3] * 0.25)


def test_grid_targeted_treatment_defaults_to_infested_sources():
    grid = _grid_with_source_and_target()
    service = SimulationService()
    service._cell_state = CellState

    summary = service._apply_treatments_to_grid(
        grid,
        [{
            "coverage": "targeted",
            "treatment_type": "targeted_spray",
            "efficacy": 0.65,
        }],
    )

    assert summary["application_count"] == 1
    assert summary["treated_tree_count"] == 1
    assert grid.treatment_active[2, 2]
    assert not grid.treatment_active[2, 3]
    assert grid.treatment_source_factor[2, 2] == pytest.approx(0.35)


def test_grid_sanitation_can_reduce_source_without_susceptibility_effect():
    grid = _grid_with_source_and_target()
    service = SimulationService()
    service._cell_state = CellState

    summary = service._apply_treatments_to_grid(
        grid,
        [{
            "coverage": "targeted",
            "treatment_type": "sanitation",
            "efficacy": 0.0,
            "source_reduction": 0.80,
        }],
    )

    assert summary["application_count"] == 1
    assert summary["treated_tree_count"] == 1
    assert grid.treatment_susceptibility_factor[2, 2] == pytest.approx(1.0)
    assert grid.treatment_source_factor[2, 2] == pytest.approx(0.20)


def test_tree_graph_treatment_reduces_target_risk():
    graph = TreeGraph(
        [
            TreeNode(0, "src", 0.0, 0.0, 0.0, 0.0, 3.0, TreeState.INFESTED),
            TreeNode(1, "dst", 0.0, 0.0, 2.0, 0.0, 3.0, TreeState.SUSCEPTIBLE),
        ],
        max_dist=10.0,
    )
    weather = WeatherTimeSeries.synthetic(hours=1)

    untreated = TreeGraphEngine(graph, weather=weather)
    untreated._accumulate_risks(math.radians(0.0))
    untreated_risk = untreated.graph.nodes[1].risk

    graph.nodes[1].treatment_susceptibility_factor = 0.25
    graph.nodes[1].treatment_active = True
    treated = TreeGraphEngine(graph, weather=weather)
    treated._accumulate_risks(math.radians(0.0))

    assert treated.graph.nodes[1].risk == pytest.approx(untreated_risk * 0.25)
    assert treated.graph.nodes[1].treatment_active is True


def test_tree_graph_targeted_treatment_defaults_to_infested_sources():
    graph = TreeGraph(
        [
            TreeNode(0, "src", 0.0, 0.0, 0.0, 0.0, 3.0, TreeState.INFESTED),
            TreeNode(1, "dst", 0.0, 0.0, 2.0, 0.0, 3.0, TreeState.SUSCEPTIBLE),
        ],
        max_dist=10.0,
    )
    service = SimulationService()

    summary = service._apply_treatments_to_tree_graph(
        graph,
        [{
            "coverage": "targeted",
            "treatment_type": "targeted_spray",
            "efficacy": 0.65,
        }],
    )

    assert summary["application_count"] == 1
    assert summary["treated_tree_count"] == 1
    assert graph.nodes[0].treatment_active is True
    assert graph.nodes[1].treatment_active is False
    assert graph.nodes[0].treatment_source_factor == pytest.approx(0.35)


def test_simulation_response_reports_treatment_summary_and_feature_flags():
    orchard_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [122.0 + col * 0.00009, 10.0],
                },
                "properties": {"Tree_ID": f"T{col}", "Status": "Unbagged"},
            }
            for col in range(3)
        ],
    }
    request = SimulationRequest(
        pest_type="fruitfly",
        orchard_geojson=orchard_geojson,
        hours=1,
        orchard_stage="mature",
        random_seed=42,
        treatment_applications=[{
            "coverage": "whole_orchard",
            "treatment_type": "targeted_spray",
            "efficacy": 0.65,
        }],
    )

    response = asyncio.get_event_loop().run_until_complete(
        SimulationService().run_simulation(request, weather_data=None)
    )

    summary = response.metadata.treatment_summary
    assert summary["application_count"] == 1
    assert summary["treated_tree_count"] == 3
    assert any(
        feature["properties"].get("treated")
        for feature in response.risk_geojson["features"]
    )
