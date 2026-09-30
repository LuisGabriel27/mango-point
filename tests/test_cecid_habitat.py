import json
from math import cos, pi
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from core.biological_rules import CecidFlyGate
from core.cecid_habitat import (
    CecidHabitatEdge,
    CecidHabitatNetwork,
    CecidHabitatNode,
    CecidHabitatTracker,
    cecid_distance_factor,
    cecid_wind_activity,
    cecid_wind_assist_strength,
    cecid_wind_direction_factor,
    cecid_wind_survival,
)
from core.config import CellState, OrchardStage
from core.grid import OrchardGrid
from core.simulation_engine import SimulationEngine
from core.tree_graph_model import TreeGraph, TreeGraphEngine, TreeNode, TreeState
from api.models.schemas import SimulationRequest
from api.services.simulation_service import SimulationService
from utils.weather_builder import build_manual_antecedent_weather, build_weather_series
from utils.weather import WeatherTimeSeries


LON = 122.58
LAT = 10.585
METRES_LON = 111_132.0 * cos(LAT * pi / 180.0)


def _position(east_m: float, north_m: float = 0.0):
    return LON + east_m / METRES_LON, LAT + north_m / 111_132.0


def _weather(
    hour: int = 18,
    wind_speed_ms: float = 1.0,
    wind_from_deg: float = 270.0,
    hours: int = 1,
):
    timestamp = pd.Timestamp(f"2026-04-01T{hour:02d}:00:00+08:00")
    return WeatherTimeSeries(pd.DataFrame({
        "datetime": [timestamp + pd.Timedelta(hours=index) for index in range(hours)],
        "wind_speed_ms": [wind_speed_ms] * hours,
        "wind_dir_deg": [wind_from_deg] * hours,
        "temperature_c": [28.0] * hours,
        "rainfall_mm": [0.0] * hours,
    }), source="test")


def _chain_network(relay_efficiency: float = 1.0, density: str = "dense"):
    network = CecidHabitatNetwork()
    nodes = [
        CecidHabitatNode("source", "source", "soil", 0.0, 0.0),
        CecidHabitatNode("relay-a", "relay", None, 10.0, 0.0, density, relay_efficiency),
        CecidHabitatNode("relay-b", "relay", None, 20.0, 0.0, density, relay_efficiency),
        CecidHabitatNode("target", "target", "tree", 30.0, 0.0),
    ]
    network.nodes = {node.node_id: node for node in nodes}
    network.source_nodes = {"soil": "source"}
    network.target_nodes = {"tree": "target"}
    network.adjacency = {
        "source": [CecidHabitatEdge("relay-a", 10.0, 90.0)],
        "relay-a": [CecidHabitatEdge("relay-b", 10.0, 90.0)],
        "relay-b": [CecidHabitatEdge("target", 10.0, 90.0)],
        "target": [],
    }
    network.zone_count = 1
    network.zone_density_counts[density] = 1
    return network


def test_wind_uses_soft_activity_and_separate_downwind_assistance():
    assert cecid_wind_activity(5.0 / 3.6) == pytest.approx(1.0)
    assert cecid_wind_activity(8.0 / 3.6) == pytest.approx(0.8)
    assert cecid_wind_activity(3.0) == pytest.approx(
        1.0 / (1.0 + (((10.8 - 5.0) / 6.0) ** 2))
    )
    assert 0.5 < cecid_wind_activity(3.0) < 0.55
    assert 0.0 < cecid_wind_activity(12.0 / 3.6) < cecid_wind_activity(8.0 / 3.6)
    assert cecid_wind_survival(3.0) == cecid_wind_activity(3.0)

    # Below the provisional controlled-flight reference there is no drift bias.
    controlled = 3.2 / 3.6
    assert cecid_wind_assist_strength(controlled) == pytest.approx(0.0)
    assert cecid_wind_direction_factor(controlled, 270.0, 90.0) == pytest.approx(1.0)

    moderate = 3.0
    downwind = cecid_wind_direction_factor(moderate, 270.0, 90.0)
    crosswind = cecid_wind_direction_factor(moderate, 270.0, 0.0)
    upwind = cecid_wind_direction_factor(moderate, 270.0, 270.0)
    assert downwind > crosswind > upwind

    full_bias = 15.0 / 3.6
    downwind = cecid_wind_direction_factor(full_bias, 270.0, 90.0)
    crosswind = cecid_wind_direction_factor(full_bias, 270.0, 0.0)
    upwind = cecid_wind_direction_factor(full_bias, 270.0, 270.0)
    assert downwind == pytest.approx(1.35)
    assert crosswind == pytest.approx(1.0)
    assert upwind == pytest.approx(0.65)


def test_three_ms_wind_limits_but_does_not_nearly_disable_a_favorable_gate():
    gate = CecidFlyGate()
    components = gate.suitability_components(
        wind_speed_ms=3.0,
        rainfall_mm=0.0,
        rainfall_history=[0.0] * 68 + [2.0] * 4,
        orchard_stage=OrchardStage.FRUITLET,
        hour=18,
    )

    assert components["hard_open"] is True
    assert components["wind_activity_score"] == pytest.approx(cecid_wind_activity(3.0))
    assert components["wind_survival_score"] == components["wind_activity_score"]
    assert components["suitability_score"] > gate.favorable_threshold
    assert "controlled flight" in components["limiting_factors"][0]


def test_cecid_distance_decay_uses_five_metre_reference():
    assert cecid_distance_factor(5.0) == pytest.approx(1.0)
    assert cecid_distance_factor(10.0) == pytest.approx(0.6)
    assert cecid_distance_factor(15.0) == pytest.approx(0.36)


def test_habitat_tracker_allows_only_one_edge_per_eligible_hour():
    tracker = CecidHabitatTracker(_chain_network())
    cohort = {"cohort-1": {"source": "soil", "pressure": 1.0}}

    assert tracker.step(cohort, True, 0.0, 0.0) == {}
    assert tracker.last_diagnostics["active_relay_count"] == 1

    # A non-eligible midday hour retains adult pressure but does not advance it.
    assert tracker.step(cohort, False, 0.0, 0.0) == {}
    assert tracker.last_diagnostics["active_relay_count"] == 1

    assert tracker.step(cohort, True, 0.0, 0.0) == {}
    arrivals = tracker.step(cohort, True, 0.0, 0.0)
    assert set(arrivals) == {"tree"}
    assert len(arrivals["tree"]) == 1


def test_dense_relay_retains_more_path_pressure_than_sparse_relay():
    cohort = {"cohort-1": {"source": "soil", "pressure": 1.0}}

    def two_hour_path(efficiency, density):
        network = _chain_network(efficiency, density)
        network.adjacency["relay-a"] = [CecidHabitatEdge("target", 10.0, 90.0)]
        tracker = CecidHabitatTracker(network)
        tracker.step(cohort, True, 0.0, 0.0)
        return tracker.step(cohort, True, 0.0, 0.0)["tree"][0]["path_efficiency"]

    sparse = two_hour_path(0.60, "sparse")
    moderate = two_hour_path(0.80, "moderate")
    dense = two_hour_path(1.00, "dense")
    assert sparse < moderate < dense


def test_overlapping_weed_zones_use_the_highest_density():
    west, south = _position(-8.0, -8.0)
    east, north = _position(8.0, 8.0)
    coordinates = [[west, south], [east, south], [east, north], [west, north]]
    network = CecidHabitatNetwork.from_lonlat(
        source_positions={"soil": _position(-12.0)},
        target_positions={"tree": _position(12.0)},
        weed_zones=[
            {"id": "sparse", "density": "sparse", "coordinates": coordinates},
            {"id": "dense", "density": "dense", "coordinates": coordinates},
        ],
    )
    relays = [node for node in network.nodes.values() if node.kind == "relay"]
    assert relays
    assert all(node.density == "dense" for node in relays)
    assert all(node.relay_efficiency == pytest.approx(1.0) for node in relays)


def test_duplicate_weed_polygons_do_not_create_extra_relays_or_edges():
    west, south = _position(-8.0, -8.0)
    east, north = _position(8.0, 8.0)
    coordinates = [[west, south], [east, south], [east, north], [west, north]]
    zone = {"id": "one", "density": "moderate", "coordinates": coordinates}
    duplicate = {**zone, "id": "duplicate"}
    kwargs = {
        "source_positions": {"soil": _position(-12.0)},
        "target_positions": {"tree": _position(12.0)},
    }

    single = CecidHabitatNetwork.from_lonlat(**kwargs, weed_zones=[zone])
    doubled = CecidHabitatNetwork.from_lonlat(**kwargs, weed_zones=[zone, duplicate])

    assert doubled.zone_count == 2
    assert doubled.resolved_habitat_component_count == 1
    assert doubled.relay_count == single.relay_count
    assert doubled.edge_count == single.edge_count


def test_network_never_connects_an_edge_beyond_fifteen_metres():
    network = CecidHabitatNetwork.from_lonlat(
        source_positions={"soil": _position(0.0)},
        target_positions={"near": _position(14.0), "far": _position(16.0)},
        weed_zones=[],
    )
    destinations = {
        network.nodes[edge.destination].key
        for edge in network.adjacency[network.source_nodes["soil"]]
    }
    assert "near" in destinations
    assert "far" not in destinations
    assert all(edge.distance_m <= 15.0 + 1e-9 for edges in network.adjacency.values() for edge in edges)


def test_weed_nodes_are_not_sources_and_tree_targets_are_mobility_nodes():
    network = CecidHabitatNetwork.from_lonlat(
        source_positions={"soil": _position(0.0)},
        target_positions={"tree-a": _position(10.0), "tree-b": _position(20.0)},
        weed_zones=[],
    )
    assert set(network.source_nodes) == {"soil"}
    assert all(node.kind != "source" for node in network.nodes.values() if node.density)
    tree_a = network.target_nodes["tree-a"]
    assert tree_a in network.adjacency
    assert any(
        network.nodes[edge.destination].key == "tree-b"
        for edge in network.adjacency[tree_a]
    )


def test_same_adult_cohort_can_rest_on_a_tree_then_make_another_short_hop():
    network = CecidHabitatNetwork.from_lonlat(
        source_positions={"soil": _position(0.0)},
        target_positions={"tree-a": _position(10.0), "tree-b": _position(20.0)},
        weed_zones=[],
    )
    tracker = CecidHabitatTracker(network)
    cohorts = {"cohort-1": {"source": "soil", "pressure": 1.0}}

    first_window = tracker.step(cohorts, True, 0.0, 0.0)
    assert set(first_window) == {"tree-a"}
    assert "tree-b" not in first_window

    # The second edge is available only at the next eligible hour. It is the
    # original cohort moving onward, not a cohort emitted by newly infested fruit.
    second_window = tracker.step(cohorts, True, 0.0, 0.0)
    assert "tree-b" in second_window
    assert second_window["tree-b"][0]["cohort_id"] == "cohort-1"
    assert second_window["tree-b"][0]["path_efficiency"] == pytest.approx(0.36)
    assert tracker.last_diagnostics["active_tree_rest_count"] == 2
    assert tracker.last_diagnostics["tree_resting_efficiency"] == pytest.approx(1.0)
    assert set(network.source_nodes) == {"soil"}


def _run_grid_habitat(
    neighbor_threat=0.0,
    hour=18,
    target_stage=OrchardStage.FRUITLET,
    wet=True,
    local_source=True,
):
    grid = OrchardGrid(3, 3, cell_size_m=5.0)
    grid.set_state(1, 1, CellState.INFESTED)
    grid.set_state(1, 2, CellState.UNBAGGED)
    if neighbor_threat:
        grid.set_neighbor_threat_uniform(neighbor_threat)
    stage_grid = np.full((3, 3), int(OrchardStage.FRUITLET), dtype=np.int32)
    stage_grid[1, 2] = int(target_stage)
    network = CecidHabitatNetwork.from_lonlat(
        source_positions={(1, 1): _position(0.0)},
        target_positions={(1, 2): _position(5.0)},
        weed_zones=[],
    )
    history = ([0.0] * 68 + [2.0] * 4) if wet else [0.0] * 72
    engine = SimulationEngine(
        grid=grid,
        weather=_weather(hour=hour),
        transition_mode="threshold",
        threshold=2.0,
        gates=[CecidFlyGate(latitude=LAT, longitude=LON)],
        orchard_stage=OrchardStage.FRUITLET,
        initial_rainfall_history=history,
        stage_grid=stage_grid,
        cecid_source_pressures={(1, 1): 1.0} if local_source else {},
        cecid_habitat_network=network,
    )
    result = engine.run(n_steps=1, progress=False)
    return result.snapshots[0]["risk"][1, 2], engine.cecid_habitat_diagnostics[0]


def test_neighbor_pressure_is_external_but_still_requires_valid_weather_and_gates():
    baseline, baseline_diag = _run_grid_habitat()
    boosted, boosted_diag = _run_grid_habitat(neighbor_threat=1.0)
    no_cohort, no_cohort_diag = _run_grid_habitat(
        neighbor_threat=1.0,
        local_source=False,
    )
    dry_soil, dry_soil_diag = _run_grid_habitat(
        neighbor_threat=1.0,
        wet=False,
        local_source=False,
    )
    midday, _ = _run_grid_habitat(neighbor_threat=1.0, hour=12)
    wrong_stage, _ = _run_grid_habitat(
        neighbor_threat=1.0,
        target_stage=OrchardStage.MATURE,
    )

    assert baseline > 0.0
    assert boosted > baseline
    assert boosted_diag["neighbor_contribution"] > 0.0
    assert no_cohort > 0.0
    assert no_cohort_diag["neighbor_contribution"] > 0.0
    assert no_cohort_diag["external_neighbor_exposed_tree_count"] == 1
    assert no_cohort_diag["habitat_limiting_reasons"] == []
    assert dry_soil == 0.0
    assert dry_soil_diag["neighbor_contribution"] == 0.0
    assert midday == 0.0
    assert wrong_stage == 0.0
    assert baseline_diag["reachable_tree_count"] == 1


def test_grid_and_tree_graph_use_the_same_direct_habitat_probability():
    grid_risk, _ = _run_grid_habitat()

    source = TreeNode(0, "source", *_position(0.0), 0.0, 0.0, 2.0, TreeState.INFESTED)
    target = TreeNode(1, "target", *_position(5.0), 5.0, 0.0, 2.0, TreeState.SUSCEPTIBLE)
    graph = TreeGraph([source, target], max_dist=15.0)
    network = CecidHabitatNetwork.from_lonlat(
        source_positions={0: _position(0.0)},
        target_positions={1: _position(5.0)},
        weed_zones=[],
    )
    engine = TreeGraphEngine(
        graph=graph,
        weather=_weather(),
        transition_mode="threshold",
        threshold=2.0,
        gates=[CecidFlyGate(latitude=LAT, longitude=LON)],
        orchard_stage=OrchardStage.FRUITLET,
        pest_type="cecid",
        initial_rainfall_history=[0.0] * 68 + [2.0] * 4,
        stage_per_tree=[OrchardStage.FRUITLET, OrchardStage.FRUITLET],
        cecid_source_pressures={0: 1.0},
        cecid_habitat_network=network,
    )
    tree_result = engine.run(n_steps=1)
    assert tree_result.snapshots[0]["risks"][1] == pytest.approx(grid_risk, rel=1e-9)
    assert tree_result.snapshots[0]["cecid_cumulative_probability"][1] == pytest.approx(
        grid_risk, rel=1e-9,
    )
    assert tree_result.snapshots[0]["cecid_exposure_hours"][1] == 1
    assert tree_result.snapshots[0]["cecid_local_exposure_hours"][1] == 1


def test_grid_and_tree_graph_use_the_same_external_neighbor_probability():
    grid_risk, grid_diagnostics = _run_grid_habitat(
        neighbor_threat=1.0,
        local_source=False,
    )

    source = TreeNode(0, "source", *_position(0.0), 0.0, 0.0, 2.0, TreeState.INFESTED)
    target = TreeNode(1, "target", *_position(5.0), 5.0, 0.0, 2.0, TreeState.SUSCEPTIBLE)
    network = CecidHabitatNetwork.from_lonlat(
        source_positions={0: _position(0.0)},
        target_positions={1: _position(5.0)},
        weed_zones=[],
    )
    engine = TreeGraphEngine(
        graph=TreeGraph([source, target], max_dist=15.0),
        weather=_weather(),
        transition_mode="threshold",
        threshold=2.0,
        gates=[CecidFlyGate(latitude=LAT, longitude=LON)],
        orchard_stage=OrchardStage.FRUITLET,
        pest_type="cecid",
        initial_rainfall_history=[0.0] * 68 + [2.0] * 4,
        stage_per_tree=[OrchardStage.FRUITLET, OrchardStage.FRUITLET],
        cecid_source_pressures={},
        cecid_habitat_network=network,
        neighbor_threat=1.0,
    )

    tree_result = engine.run(n_steps=1)
    tree_diagnostics = engine.cecid_habitat_diagnostics[0]

    assert tree_result.snapshots[0]["risks"][1] == pytest.approx(grid_risk, rel=1e-9)
    assert grid_diagnostics["external_neighbor_exposed_tree_count"] == 1
    assert tree_diagnostics["external_neighbor_exposed_tree_count"] == 1
    assert tree_diagnostics["external_neighbor_contribution"] == pytest.approx(
        grid_diagnostics["external_neighbor_contribution"], rel=1e-9,
    )


def test_grid_and_tree_graph_use_the_same_multi_hour_tree_resting_path():
    grid = OrchardGrid(1, 5, cell_size_m=5.0)
    grid.set_state(0, 0, CellState.INFESTED)
    grid.set_state(0, 2, CellState.UNBAGGED)
    grid.set_state(0, 4, CellState.UNBAGGED)
    stage_grid = np.full((1, 5), int(OrchardStage.FRUITLET), dtype=np.int32)
    grid_network = CecidHabitatNetwork.from_lonlat(
        source_positions={(0, 0): _position(0.0)},
        target_positions={(0, 2): _position(10.0), (0, 4): _position(20.0)},
        weed_zones=[],
    )
    grid_engine = SimulationEngine(
        grid=grid,
        weather=_weather(hours=2),
        transition_mode="threshold",
        threshold=2.0,
        gates=[CecidFlyGate(latitude=LAT, longitude=LON)],
        orchard_stage=OrchardStage.FRUITLET,
        initial_rainfall_history=[0.0] * 68 + [2.0] * 4,
        stage_grid=stage_grid,
        cecid_source_pressures={(0, 0): 1.0},
        cecid_habitat_network=grid_network,
    )
    grid_result = grid_engine.run(n_steps=2, progress=False)

    source = TreeNode(0, "source", *_position(0.0), 0.0, 0.0, 2.0, TreeState.INFESTED)
    first = TreeNode(1, "first", *_position(10.0), 10.0, 0.0, 2.0, TreeState.SUSCEPTIBLE)
    second = TreeNode(2, "second", *_position(20.0), 20.0, 0.0, 2.0, TreeState.SUSCEPTIBLE)
    tree_network = CecidHabitatNetwork.from_lonlat(
        source_positions={0: _position(0.0)},
        target_positions={1: _position(10.0), 2: _position(20.0)},
        weed_zones=[],
    )
    tree_engine = TreeGraphEngine(
        graph=TreeGraph([source, first, second], max_dist=15.0),
        weather=_weather(hours=2),
        transition_mode="threshold",
        threshold=2.0,
        gates=[CecidFlyGate(latitude=LAT, longitude=LON)],
        orchard_stage=OrchardStage.FRUITLET,
        pest_type="cecid",
        initial_rainfall_history=[0.0] * 68 + [2.0] * 4,
        stage_per_tree=[OrchardStage.FRUITLET] * 3,
        cecid_source_pressures={0: 1.0},
        cecid_habitat_network=tree_network,
    )
    tree_result = tree_engine.run(n_steps=2)

    assert grid_result.snapshots[0]["risk"][0, 4] == 0.0
    assert tree_result.snapshots[0]["risks"][2] == 0.0
    assert grid_result.snapshots[1]["risk"][0, 4] > 0.0
    assert tree_result.snapshots[1]["risks"][2] == pytest.approx(
        grid_result.snapshots[1]["risk"][0, 4], rel=1e-9,
    )


def test_independent_cohorts_combine_but_duplicate_branches_take_maximum_path():
    network = _chain_network()
    network.adjacency = {
        "source": [
            CecidHabitatEdge("relay-a", 10.0, 90.0),
            CecidHabitatEdge("relay-b", 10.0, 90.0),
        ],
        "relay-a": [CecidHabitatEdge("target", 10.0, 90.0)],
        "relay-b": [CecidHabitatEdge("target", 10.0, 90.0)],
    }
    tracker = CecidHabitatTracker(network)
    cohorts = {
        "cohort-1": {"source": "soil", "pressure": 1.0},
        "cohort-2": {"source": "soil", "pressure": 0.5},
    }
    tracker.step(cohorts, True, 0.0, 0.0)
    arrivals = tracker.step(cohorts, True, 0.0, 0.0)["tree"]
    assert len(arrivals) == 2
    assert {arrival["cohort_id"] for arrival in arrivals} == set(cohorts)


def test_antecedent_weather_warms_up_and_retains_weed_relay_pressure():
    network = _chain_network()
    source_node = network.nodes["source"]
    target_node = network.nodes["target"]
    network.nodes["source"] = CecidHabitatNode(
        source_node.node_id, source_node.kind, 0, source_node.x, source_node.y,
    )
    network.nodes["target"] = CecidHabitatNode(
        target_node.node_id, target_node.kind, 1, target_node.x, target_node.y,
    )
    network.source_nodes = {0: "source"}
    network.target_nodes = {1: "target"}

    source = TreeNode(0, "source", *_position(0.0), 0.0, 0.0, 2.0, TreeState.INFESTED)
    target = TreeNode(1, "target", *_position(30.0), 30.0, 0.0, 2.0, TreeState.SUSCEPTIBLE)
    antecedent = [
        {
            "datetime": "2026-04-01T17:00:00+08:00",
            "hour": 17,
            "temperature_c": 28.0,
            "wind_speed_ms": 0.0,
            "wind_dir_deg": 0.0,
            "rainfall_mm": 2.0,
        },
        {
            "datetime": "2026-04-01T18:00:00+08:00",
            "hour": 18,
            "temperature_c": 28.0,
            "wind_speed_ms": 0.0,
            "wind_dir_deg": 0.0,
            "rainfall_mm": 0.0,
        },
        {
            "datetime": "2026-04-01T19:00:00+08:00",
            "hour": 19,
            "temperature_c": 28.0,
            "wind_speed_ms": 0.0,
            "wind_dir_deg": 0.0,
            "rainfall_mm": 0.0,
        },
    ]
    engine = TreeGraphEngine(
        graph=TreeGraph([source, target], max_dist=15.0),
        weather=_weather(hour=6),
        gates=[CecidFlyGate(latitude=LAT, longitude=LON)],
        orchard_stage=OrchardStage.FRUITLET,
        pest_type="cecid",
        initial_rainfall_history=[entry["rainfall_mm"] for entry in antecedent],
        cecid_antecedent_weather=antecedent,
        stage_per_tree=[OrchardStage.FRUITLET, OrchardStage.FRUITLET],
        cecid_source_pressures={0: 1.0},
        cecid_habitat_network=network,
    )

    active_relays = {
        relay_id
        for state in engine.cecid_habitat_tracker.relay_state.values()
        for relay_id in state
    }
    assert "relay-a" in active_relays
    assert "relay-b" in active_relays
    assert len(engine.cecid_cohort_events) == 1


@pytest.mark.asyncio
async def test_bundled_orchard_weather_preset_spreads_and_replays_with_same_seed():
    orchard_path = (
        Path(__file__).resolve().parents[1]
        / "frontend" / "src" / "assets" / "guimaras-wonders-farm-trees.json"
    )
    orchard = json.loads(orchard_path.read_text(encoding="utf-8"))
    blocks = []
    for day in range(7):
        start = day * 24
        blocks.extend([
            {
                "start_hour": start,
                "end_hour": start + 4,
                "temperature_c": 26.0,
                "wind_speed_ms": 1.0,
                "wind_dir_deg": 90.0,
                "rainfall_mm": 2.0,
            },
            {
                "start_hour": start + 4,
                "end_hour": start + 24,
                "temperature_c": 28.0,
                "wind_speed_ms": 1.0,
                "wind_dir_deg": 90.0,
                "rainfall_mm": 0.0,
            },
        ])
    request = SimulationRequest(
        pest_type="cecid",
        orchard_geojson=orchard,
        hours=168,
        orchard_stage="fruitlet",
        random_seed=1,
        manual_weather_start="2026-04-01T00:00:00+08:00",
        manual_weather_blocks=blocks,
        manual_soil_context={"preset": "dry"},
        include_time_series=False,
    )
    weather = build_weather_series(request)
    antecedent = build_manual_antecedent_weather(request)
    coordinates = {"lat": 10.631031789835638, "lon": 122.61253175014424}

    first = await SimulationService().run_simulation(
        request,
        weather_data=weather,
        weather_context=antecedent,
        orchard_coordinates=coordinates,
    )
    replay = await SimulationService().run_simulation(
        request,
        weather_data=weather,
        weather_context=antecedent,
        orchard_coordinates=coordinates,
    )

    assert first.metadata.initial_infected_count == 0
    assert 1 <= first.metadata.cecid_assumed_source_count <= 3
    # Model v4 regression: the bundled preset produces useful spread from the
    # deterministic assumed soil sources without inflating the source count.
    assert first.n_infested_final == 51
    assert first.metadata.n_newly_infested == first.n_infested_final
    assert replay.n_infested_final == first.n_infested_final
    assert replay.metadata.cecid_sources == first.metadata.cecid_sources
