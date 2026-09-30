import numpy as np

from api.models.schemas import PestTypeEnum, SimulationRequest
from api.services.simulation_service import SimulationService
from core.config import CellState
from core.grid import OrchardGrid
from core.tree_graph_model import TreeGraph, TreeNode, TreeState


def _seeded_grid(direction, threat):
    svc = SimulationService()
    grid = OrchardGrid(rows=5, cols=5, cell_size_m=1.0)
    grid.plant_trees(np.ones((5, 5), dtype=bool), CellState.UNBAGGED)

    seed_info = svc._seed_default_infestation(
        grid=grid,
        pest_type=PestTypeEnum.CECID,
        orchard_stage="fruitlet",
        random_seed=42,
        neighbor_threat=threat,
        neighbor_direction=direction,
    )
    return grid, seed_info


def test_cecid_grid_neighbor_pressure_does_not_relabel_external_arrivals_as_soil_sources():
    grid, seed_info = _seeded_grid(direction="N", threat=0.30)

    assert seed_info["strategy"] == "assumed_soil_random_susceptible"
    assert 1 <= seed_info["count"] <= 3
    for cell in seed_info["cells"]:
        assert grid.state[cell["row"], cell["col"]] == CellState.UNBAGGED
    assert int(grid.infested_mask.sum()) == 0


def test_cecid_grid_internal_source_fallback_is_independent_of_neighbor_direction():
    _, north = _seeded_grid(direction="N", threat=0.30)
    grid, northeast = _seeded_grid(direction="NE", threat=0.80)

    assert northeast["strategy"] == "assumed_soil_random_susceptible"
    assert northeast["cells"] == north["cells"]
    for cell in northeast["cells"]:
        assert grid.state[cell["row"], cell["col"]] == CellState.UNBAGGED


def test_grid_auto_seed_keeps_random_fallback_without_direction():
    grid, seed_info = _seeded_grid(direction=None, threat=0.80)

    assert seed_info["strategy"] == "assumed_soil_random_susceptible"
    assert 1 <= seed_info["count"] <= 3
    assert int(grid.infested_mask.sum()) == 0


def test_cecid_assumed_source_selection_is_reproducible_and_limited_to_three():
    svc = SimulationService()
    selections = []
    for _ in range(2):
        grid = OrchardGrid(rows=5, cols=5, cell_size_m=1.0)
        grid.plant_trees(np.ones((5, 5), dtype=bool), CellState.UNBAGGED)
        seed_info = svc._seed_default_infestation(
            grid=grid,
            pest_type=PestTypeEnum.CECID,
            orchard_stage="fruitlet",
            random_seed=20260822,
        )
        selections.append(seed_info["cells"])
        assert 1 <= seed_info["count"] <= 3
        assert int(grid.infested_mask.sum()) == 0

    assert selections[0] == selections[1]


def test_fruit_fly_fallback_still_creates_initial_infestation():
    svc = SimulationService()
    grid = OrchardGrid(rows=5, cols=5, cell_size_m=1.0)
    grid.plant_trees(np.ones((5, 5), dtype=bool), CellState.UNBAGGED)

    seed_info = svc._seed_default_infestation(
        grid=grid,
        pest_type=PestTypeEnum.FRUITFLY,
        orchard_stage="mature",
        random_seed=42,
    )

    assert seed_info["strategy"] == "random_susceptible"
    assert 1 <= seed_info["count"] <= 3
    assert int(grid.infested_mask.sum()) == seed_info["count"]


def test_tree_graph_cecid_fallback_is_a_source_anchor_not_an_infected_tree():
    svc = SimulationService()
    graph = TreeGraph(
        [
            TreeNode(0, "T0", 0, 0, 0.0, 0.0, 2.5),
            TreeNode(1, "T1", 0, 0, 10.0, 0.0, 2.5),
        ],
        max_dist=50.0,
    )

    seed_info = svc._seed_tree_graph_infestation(
        graph=graph,
        pest_type=PestTypeEnum.CECID,
        orchard_stage="fruitlet",
        random_seed=42,
        tree_overrides=None,
    )

    assert seed_info["strategy"] == "assumed_soil_random_susceptible"
    assert 1 <= seed_info["count"] <= 2
    assert len(seed_info["node_indices"]) == seed_info["count"]
    assert graph.n_infested() == 0


def test_existing_cecid_infestation_prevents_extra_assumed_sources():
    svc = SimulationService()
    grid = OrchardGrid(rows=3, cols=3, cell_size_m=1.0)
    grid.plant_trees(np.ones((3, 3), dtype=bool), CellState.UNBAGGED)
    grid.set_state(1, 1, CellState.INFESTED)

    seed_info = svc._seed_default_infestation(
        grid=grid,
        pest_type=PestTypeEnum.CECID,
        orchard_stage="fruitlet",
        random_seed=42,
    )

    assert seed_info["strategy"] == "existing_infestation"
    assert seed_info["count"] == 0
    assert int(grid.infested_mask.sum()) == 1


def test_tree_graph_auto_seed_uses_neighbor_facing_tree_when_direction_is_known():
    svc = SimulationService()
    graph = TreeGraph(
        [
            TreeNode(0, "W", 0, 0, -10.0, 0.0, 2.5),
            TreeNode(1, "C", 0, 0, 0.0, 0.0, 2.5),
            TreeNode(2, "E", 0, 0, 10.0, 0.0, 2.5),
        ],
        max_dist=50.0,
    )

    seed_info = svc._seed_tree_graph_infestation(
        graph=graph,
        pest_type=PestTypeEnum.FRUITFLY,
        orchard_stage="mature",
        random_seed=42,
        tree_overrides=None,
        neighbor_threat=0.30,
        neighbor_direction="E",
    )

    assert seed_info["strategy"] == "neighbor_edge_E"
    assert seed_info["tree_ids"] == ["E"]
    assert seed_info["count"] == 1
    assert graph.nodes[2].state == TreeState.INFESTED
    assert graph.nodes[0].state == TreeState.SUSCEPTIBLE


def test_tree_graph_auto_seed_skips_when_pest_inactive_for_stage():
    svc = SimulationService()
    graph = TreeGraph(
        [TreeNode(0, "T1", 0, 0, 0.0, 0.0, 2.5)],
        max_dist=50.0,
    )

    seed_info = svc._seed_tree_graph_infestation(
        graph=graph,
        pest_type=PestTypeEnum.CECID,
        orchard_stage="mature",
        random_seed=42,
        tree_overrides=None,
        neighbor_threat=1.0,
        neighbor_direction="N",
    )

    assert seed_info["strategy"] == "none_inactive_stage"
    assert seed_info["count"] == 0
    assert graph.nodes[0].state == TreeState.SUSCEPTIBLE


def test_simulation_metadata_reports_neighbor_edge_seed_source():
    import asyncio

    orchard_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [122.0 + col * 0.00009, 10.0 + row * 0.00009],
                },
                "properties": {"Tree_ID": f"T{row}{col}", "Status": "Unbagged"},
            }
            for row in range(2)
            for col in range(3)
        ],
    }
    request = SimulationRequest(
        pest_type="fruitfly",
        orchard_geojson=orchard_geojson,
        hours=1,
        orchard_stage="mature",
        random_seed=42,
        neighbor_threat=0.3,
        neighbor_direction="E",
    )

    response = asyncio.get_event_loop().run_until_complete(
        SimulationService().run_simulation(request, weather_data=None)
    )

    assert response.metadata.initial_seed_strategy == "neighbor_edge_E"
    assert response.metadata.initial_seed_count == 1
    assert response.metadata.initial_seed_cells


def test_cecid_metadata_separates_assumed_soil_sources_from_infected_fruit():
    import asyncio

    orchard_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [122.58 + index * 0.00005, 10.585],
                },
                "properties": {"Tree_ID": f"T{index}", "Status": "Unbagged"},
            }
            for index in range(6)
        ],
    }
    request = SimulationRequest(
        pest_type="cecid",
        orchard_geojson=orchard_geojson,
        hours=1,
        orchard_stage="fruitlet",
        random_seed=20260822,
    )

    response = asyncio.get_event_loop().run_until_complete(
        SimulationService().run_simulation(request, weather_data=None)
    )

    assert response.metadata.initial_seed_strategy == "assumed_soil_random_susceptible"
    assert response.metadata.initial_seed_count == 0
    assert response.metadata.initial_infected_count == 0
    assert response.metadata.initial_seed_cells == []
    assert 1 <= response.metadata.cecid_source_count <= 3
    assert response.metadata.cecid_assumed_source_count == response.metadata.cecid_source_count
    assert response.metadata.cecid_explicit_source_count == 0
    assert response.metadata.n_newly_infested == response.n_infested_final
    assert all(source["assumed"] for source in response.metadata.cecid_sources)
