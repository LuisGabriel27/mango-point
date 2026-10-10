from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from api.models.schemas import SimulationRequest
from api.models.schemas import PestTypeEnum
from api.routes.simulation import (
    _attach_cecid_uncertainty_summary,
    _cecid_uncertainty_seed,
    _summarize_cecid_uncertainty_samples,
)
from api.services.simulation_service import SimulationService, simulation_service
from core.biological_rules import CecidFlyGate, CecidSourceCohortModel
from core.cecid_habitat import CecidHabitatNetwork
from core.config import CellState, OrchardStage
from core.grid import OrchardGrid
from core.tree_graph_model import TreeGraph, TreeGraphEngine, TreeNode, TreeState
from utils.weather import WeatherTimeSeries


def test_cecid_uncertainty_summary_is_replay_stable_and_explicitly_not_validation():
    seeds = [_cecid_uncertainty_seed(42, index) for index in range(5)]
    assert seeds == [_cecid_uncertainty_seed(42, index) for index in range(5)]
    assert len(set(seeds)) == 5

    samples = [
        {
            "seed": seed,
            "n_infested_final": count,
            "source_count": source_count,
            "assumed_source_count": source_count,
            "source_tree_ids": [],
            "infested_tree_ids": ["T1", "T2"] if count >= 24 else ["T1"],
        }
        for seed, count, source_count in zip(seeds, [6, 24, 28, 31, 36], [1, 2, 2, 3, 3])
    ]
    summary = _summarize_cecid_uncertainty_samples(samples, map_seed=42)

    assert summary["runs"] == 5
    assert summary["minimum"] == 6
    assert summary["median"] == 28
    assert summary["maximum"] == 36
    assert summary["assumed_source_count_min"] == 1
    assert summary["assumed_source_count_max"] == 3
    assert summary["uncertainty_type"] == "assumed_source_placement_and_stochastic_establishment"
    assert summary["tree_infestation_counts"]["T1"] == 5
    assert summary["tree_infestation_frequencies"]["T1"] == pytest.approx(1.0)
    assert summary["tree_infestation_counts"]["T2"] == 4
    assert summary["tree_infestation_frequencies"]["T2"] == pytest.approx(0.8)
    assert "not a calibrated confidence interval" in summary["interpretation"]


@pytest.mark.asyncio
async def test_cecid_uncertainty_annotates_each_tree_for_likelihood_mapping():
    orchard = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [122.5800, 10.5850]},
                "properties": {"Tree_ID": "T1"},
            },
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [122.58005, 10.5850]},
                "properties": {"Tree_ID": "T2"},
            },
        ],
    }
    request = SimulationRequest(
        pest_type="cecid",
        orchard_geojson=orchard,
        orchard_stage="fruitlet",
        hours=1,
        random_seed=42,
        cecid_uncertainty_runs=3,
    )
    weather = [{
        "datetime": "2026-04-01T12:00:00+08:00",
        "hour": 12,
        "wind_speed_ms": 1.0,
        "wind_dir_deg": 90.0,
        "temperature_c": 28.0,
        "rainfall_mm": 0.0,
    }]
    coordinates = {"lat": 10.585, "lon": 122.58}
    primary = await simulation_service.run_simulation(
        request=request,
        weather_data=weather,
        weather_context=[],
        orchard_coordinates=coordinates,
    )

    await _attach_cecid_uncertainty_summary(
        result=primary,
        request=request,
        weather_data=weather,
        weather_context=[],
        weather_provenance={"provider": "test"},
        orchard_coordinates=coordinates,
    )

    summary = primary.metadata.cecid_uncertainty_summary
    assert summary["runs"] == 3
    for feature in primary.risk_geojson["features"]:
        properties = feature["properties"]
        assert properties["ensemble_runs"] == 3
        assert 0.0 <= properties["ensemble_infestation_frequency"] <= 1.0
    for snapshot in primary.time_series:
        assert all(
            feature["properties"]["ensemble_runs"] == 3
            for feature in snapshot.risk_geojson["features"]
        )


def _weather(hours=2, start="2026-04-01T18:00:00+08:00"):
    start_dt = pd.Timestamp(start)
    frame = pd.DataFrame({
        "datetime": [start_dt + pd.Timedelta(hours=index) for index in range(hours)],
        "wind_speed_ms": [1.0] * hours,
        "wind_dir_deg": [90.0] * hours,
        "temperature_c": [28.0] * hours,
        "rainfall_mm": [0.0] * hours,
    })
    return WeatherTimeSeries(frame, source="test")


def _node(index, x):
    return TreeNode(
        index=index,
        tree_id=f"T{index + 1}",
        lon=122.58 + x / 109_000.0,
        lat=10.585,
        x=float(x),
        y=0.0,
        crown_radius=2.5,
        state=TreeState.SUSCEPTIBLE,
    )


def test_cohorts_emit_once_decay_and_expire_at_48_hours():
    model = CecidSourceCohortModel({"soil-a": 1.0}, antecedent_rainfall=[8.0])
    active = model.step(0, "2026-04-01T18:00:00+08:00", 0.0, True)
    assert active["soil-a"] == pytest.approx(1.0)
    assert len(model.events) == 1

    # The configured soil batch emits only once.
    model.step(1, "2026-04-01T19:00:00+08:00", 0.0, True)
    assert len(model.events) == 1
    for hour in range(2, 25):
        active = model.step(hour, None, 0.0, False)
    assert active["soil-a"] == pytest.approx(0.5, rel=1e-6)

    for hour in range(25, 48):
        active = model.step(hour, None, 0.0, False)
    assert active["soil-a"] > 0.0
    active = model.step(48, None, 0.0, False)
    assert "soil-a" not in active
    assert model.lifecycle_diagnostics()["expired_cohort_count"] == 1


def test_new_rain_does_not_replenish_the_finite_soil_batch():
    model = CecidSourceCohortModel({0: 1.0}, antecedent_rainfall=[8.0])
    model.step(0, None, 0.0, True)
    model.step(1, None, 0.5, False)
    model.step(2, None, 0.0, True)
    model.step(3, None, 0.0, True)
    assert len(model.events) == 1
    assert model.lifecycle_diagnostics()["remaining_soil_batches"] == 0


def test_antecedent_replay_preserves_cohort_and_prevents_duplicate_emergence():
    model = CecidSourceCohortModel({"soil-a": 1.0})
    antecedent = [
        {
            "datetime": f"2026-04-01T{hour:02d}:00:00+08:00",
            "rainfall_mm": 2.0 if hour == 12 else 0.0,
            "eligible": hour == 18,
        }
        for hour in range(12, 24)
    ]
    active = model.warm_up(antecedent, lambda entry: entry["eligible"])

    assert len(model.events) == 1
    assert model.events[0]["antecedent"] is True
    assert active["soil-a"] == pytest.approx(2.0 ** (-5.0 / 24.0))

    model.step(0, "2026-04-02T06:00:00+08:00", 0.0, True)
    assert len(model.events) == 1


def test_tree_graph_cecid_range_is_limited_to_15_metres():
    graph = TreeGraph([_node(0, 0), _node(1, 14), _node(2, 16)], max_dist=20.0)
    engine = TreeGraphEngine(
        graph=graph,
        weather=_weather(hours=1),
        transition_mode="threshold",
        threshold=2.0,
        gates=[CecidFlyGate(latitude=10.585, longitude=122.58)],
        orchard_stage=OrchardStage.FRUITLET,
        pest_type="cecid",
        initial_rainfall_history=[0.0] * 68 + [2.0] * 4,
        stage_per_tree=[OrchardStage.FRUITLET] * 3,
        cecid_source_pressures={0: 1.0},
    )
    result = engine.run(n_steps=1)
    risks = result.snapshots[0]["risks"]
    assert risks[1] > 0.0
    assert risks[2] == 0.0


def test_newly_infested_tree_does_not_become_a_second_generation_source():
    # T1 can reach T2, and T2 can reach T3, but T1 cannot reach T3. If newly
    # infested fruit became a source, T3 would be infected in Hour 2.
    graph = TreeGraph([_node(0, 0), _node(1, 10), _node(2, 20)], max_dist=15.0)
    engine = TreeGraphEngine(
        graph=graph,
        weather=_weather(hours=2),
        transition_mode="threshold",
        threshold=0.05,
        gates=[CecidFlyGate(latitude=10.585, longitude=122.58)],
        orchard_stage=OrchardStage.FRUITLET,
        pest_type="cecid",
        lambda0=10.0,
        initial_rainfall_history=[0.0] * 68 + [2.0] * 4,
        stage_per_tree=[OrchardStage.FRUITLET] * 3,
        cecid_source_pressures={0: 1.0},
    )
    result = engine.run(n_steps=2)
    assert result.graph.nodes[1].state == TreeState.INFESTED
    assert result.graph.nodes[2].state == TreeState.SUSCEPTIBLE
    assert len(engine.cecid_cohort_events) == 1


def test_original_adult_cohort_moves_through_tree_without_creating_second_generation():
    nodes = [_node(0, 0), _node(1, 10), _node(2, 20)]
    nodes[0].state = TreeState.INFESTED
    graph = TreeGraph(nodes, max_dist=15.0)
    network = CecidHabitatNetwork.from_lonlat(
        source_positions={0: (nodes[0].lon, nodes[0].lat)},
        target_positions={
            1: (nodes[1].lon, nodes[1].lat),
            2: (nodes[2].lon, nodes[2].lat),
        },
        weed_zones=[],
    )
    engine = TreeGraphEngine(
        graph=graph,
        weather=_weather(hours=2, start="2026-04-01T18:00:00+08:00"),
        transition_mode="threshold",
        threshold=0.001,
        gates=[CecidFlyGate(latitude=10.585, longitude=122.58)],
        orchard_stage=OrchardStage.FRUITLET,
        pest_type="cecid",
        initial_rainfall_history=[0.0] * 68 + [2.0] * 4,
        stage_per_tree=[OrchardStage.FRUITLET] * 3,
        cecid_source_pressures={0: 1.0},
        cecid_habitat_network=network,
    )

    result = engine.run(n_steps=2)

    assert result.graph.nodes[1].state == TreeState.INFESTED
    assert result.graph.nodes[2].state == TreeState.INFESTED
    assert engine.cecid_cohort_model.source_pressures == {0: 1.0}
    assert len(engine.cecid_cohort_events) == 1


def test_zone_and_observation_sources_are_combined_and_map_visible():
    service = SimulationService()
    service._load_modules()
    grid = OrchardGrid(6, 6, cell_size_m=5.0)
    grid.origin_lon = 122.58
    grid.origin_lat = 10.585
    grid.set_state(1, 1, CellState.INFESTED)
    grid.tree_ids[1, 1] = "observed"
    grid.set_state(4, 4, CellState.UNBAGGED)
    grid.tree_ids[4, 4] = "zone-tree"

    m_lat = 111_132.0
    m_lon = 111_132.0 * np.cos(np.radians(10.585))
    lon = grid.origin_lon + 4.5 * 5.0 / m_lon
    lat = grid.origin_lat + 4.5 * 5.0 / m_lat
    delta = 2.0 / m_lat
    zones = [{
        "id": "wet-lowland",
        "label": "Wet lowland soil",
        "pressure": "high",
        "coordinates": [
            [lon - delta, lat - delta],
            [lon + delta, lat - delta],
            [lon + delta, lat + delta],
            [lon - delta, lat + delta],
        ],
    }]

    pressures, metadata = service._grid_cecid_sources(grid, zones)
    assert set(pressures) == {(1, 1), (4, 4)}
    assert pressures[(4, 4)] == 1.5
    assert all(item["assumed"] is False for item in metadata)
    assert grid.cecid_source_pressure[1, 1] == 1.0
    assert grid.cecid_source_pressure[4, 4] == 1.5


def test_seeded_fallback_source_is_explicitly_marked_assumed():
    service = SimulationService()
    service._load_modules()
    grid = OrchardGrid(4, 4)
    grid.origin_lon = 122.58
    grid.origin_lat = 10.585
    grid.set_state(2, 2, CellState.UNBAGGED)
    grid.tree_ids[2, 2] = "fallback-tree"

    pressures, metadata = service._grid_cecid_sources(
        grid, zones=[], assumed_source_keys=[(2, 2)],
    )
    assert pressures == {(2, 2): 1.0}
    assert metadata[0]["origin"] == "assumed_fallback"
    assert metadata[0]["assumed"] is True
    assert grid.cecid_source_assumed[2, 2]
    assert grid.state[2, 2] == CellState.UNBAGGED


def test_simulation_service_loads_only_the_selected_pest_gate():
    service = SimulationService()
    service._load_modules()
    cecid = service._get_gates(PestTypeEnum.CECID)
    fruitfly = service._get_gates(PestTypeEnum.FRUITFLY)
    assert len(cecid) == 1 and isinstance(cecid[0], CecidFlyGate)
    assert len(fruitfly) == 1
    assert type(cecid[0]) is not type(fruitfly[0])


@pytest.mark.asyncio
async def test_cecid_zones_do_not_change_fixed_seed_fruit_fly_results():
    features = [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [122.5800 + i * 0.00003, 10.585]}, "properties": {"Tree_ID": f"T{i}"}}
        for i in range(6)
    ]
    geojson = {"type": "FeatureCollection", "features": features}
    common = dict(
        pest_type="fruitfly",
        orchard_geojson=geojson,
        orchard_stage="mature",
        random_seed=2048,
        hours=8,
        simulation_mode="grid",
    )
    zone = {
        "id": "ignored-for-fruitfly",
        "label": "Research soil assumption",
        "pressure": "high",
        "coordinates": [[122.5799, 10.5849], [122.581, 10.5849], [122.581, 10.5851]],
    }
    weed_zone = {
        "id": "ignored-weeds-for-fruitfly",
        "label": "Weed habitat",
        "density": "dense",
        "coordinates": [[122.5799, 10.5849], [122.581, 10.5849], [122.581, 10.5851]],
    }
    weather = [{
        "datetime": f"2026-04-01T{hour:02d}:00:00+08:00",
        "temperature_c": 30.0,
        "wind_speed_ms": 1.0,
        "wind_dir_deg": 90.0,
        "rainfall_mm": 0.0,
    } for hour in range(8, 16)]
    service = SimulationService()
    baseline = await service.run_simulation(SimulationRequest(**common), weather_data=weather)
    with_zone = await service.run_simulation(
        SimulationRequest(
            **common,
            cecid_emergence_zones=[zone],
            cecid_weed_zones=[weed_zone],
        ),
        weather_data=weather,
    )

    assert with_zone.n_infested_final == baseline.n_infested_final
    assert with_zone.peak_risk == baseline.peak_risk
    baseline_risks = [feature["properties"]["risk"] for feature in baseline.risk_geojson["features"]]
    zone_risks = [feature["properties"]["risk"] for feature in with_zone.risk_geojson["features"]]
    assert zone_risks == baseline_risks


@pytest.mark.asyncio
async def test_cecid_result_snapshots_weeds_without_treating_them_as_sources():
    features = [
        {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [122.5800 + index * 0.000045, 10.585],
            },
            "properties": {"Tree_ID": f"T{index}"},
        }
        for index in range(5)
    ]
    weed_zone = {
        "id": "central-weeds",
        "label": "Central drainage weeds",
        "density": "dense",
        "coordinates": [
            [122.58002, 10.58496],
            [122.58016, 10.58496],
            [122.58016, 10.58504],
            [122.58002, 10.58504],
        ],
    }
    request = SimulationRequest(
        pest_type="cecid",
        orchard_geojson={"type": "FeatureCollection", "features": features},
        orchard_stage="fruitlet",
        random_seed=451,
        hours=1,
        simulation_mode="tree_graph",
        initial_infestation_tree_ids=["T0"],
        manual_weather_prefix_rain=[0.0] * 68 + [2.0] * 4,
        cecid_weed_zones=[weed_zone],
    )
    weather = [{
        "datetime": "2026-04-01T18:00:00+08:00",
        "temperature_c": 28.0,
        "wind_speed_ms": 1.0,
        "wind_dir_deg": 270.0,
        "rainfall_mm": 0.0,
    }]

    result = await SimulationService().run_simulation(request, weather_data=weather)

    assert result.metadata.cecid_weed_zones == [weed_zone]
    assert result.metadata.cecid_habitat_summary["weed_zone_count"] == 1
    assert result.metadata.cecid_habitat_summary["weed_is_source"] is False
    assert "BPI field calibration" in result.metadata.cecid_habitat_summary["research_assumption"]
    assert result.metadata.cecid_source_count == 1
    assert all(source["origin"] != "weed" for source in result.metadata.cecid_sources)
    assert result.metadata.cecid_habitat_diagnostics[0]["weed_effect_assumption"]
