"""Regression checks for fruit-only pest activity and finite Cecid cohorts."""

from collections import deque

import pandas as pd
import pytest

from api.models.schemas import ManualWeather, SimulationRequest
from core.biological_rules import CecidFlyGate, CecidSourceCohortModel, FruitFlyGate
from core.cecid_habitat import CecidHabitatNetwork
from core.config import CellState, OrchardStage
from core.grid import OrchardGrid
from core.simulation_engine import SimulationEngine
from core.tree_graph_model import TreeGraph, TreeGraphEngine, TreeNode, TreeState
from utils.weather import WeatherTimeSeries
from utils.weather_builder import build_weather_series, compute_gate_diagnostics


@pytest.mark.parametrize("capacity_hours", [4.0, 8.0, 16.0])
def test_partial_laying_retains_the_cohort_until_capacity_is_exhausted(capacity_hours):
    model = CecidSourceCohortModel({"soil": 1.0}, [8.0], egg_capacity_hours=capacity_hours)
    model.step(0, None, 0.0, True)
    cohort_id = next(iter(model.active_cohorts()))
    model.consume_oviposition({cohort_id: 0.5})
    assert model.active_cohorts()[cohort_id]["remaining_egg_capacity"] == pytest.approx(
        1.0 - 0.5 / capacity_hours,
    )
    for _ in range(int(capacity_hours * 2) - 1):
        model.consume_oviposition({cohort_id: 0.5})
    assert model.active_cohorts() == {}
    assert model.lifecycle_diagnostics()["spent_cohort_count"] == 1
    model.step(1, None, 4.0, False)
    assert model.step(2, None, 0.0, True) == {}
    assert len(model.events) == 1


def test_antecedent_replay_returns_pressure_after_egg_use():
    model = CecidSourceCohortModel({"soil": 1.0}, egg_capacity_hours=1.0)
    weather = [{"rainfall_mm": 2.0}, {"rainfall_mm": 0.0}]
    active = model.warm_up(
        weather, lambda _: True,
        lambda entry, cohorts, eligible: model.consume_oviposition({key: 1.0 for key in cohorts}),
    )
    assert active == {}
    assert model.lifecycle_diagnostics()["spent_cohort_count"] == 1


def _cecid_components(hour, cloud, wet=True):
    gate = CecidFlyGate()
    entry = {"datetime": f"2026-04-01T{hour:02d}:00:00+08:00"}
    if cloud is not None:
        entry["cloud_cover_pct"] = cloud
    entry.update(shortwave_radiation_wm2=100.0, direct_normal_irradiance_wm2=0.0)
    gate.set_weather_context(entry)
    return gate.suitability_components(
        1.0, 0.0, deque([8.0] if wet else [0.0]), OrchardStage.FRUITLET, hour,
    )


def test_cloudy_day_activity_is_soft_and_never_enables_darkness():
    missing, clear, partial, overcast = [_cecid_components(12, cloud) for cloud in (None, 0, 65, 100)]
    assert missing["hard_open"] is False
    assert missing["cloud_cover_available"] is False
    assert clear["activity_score"] == 0.0
    assert 0 < partial["activity_score"] < overcast["activity_score"] < 1.0
    assert overcast["activity_window"] == "cloudy_day"
    assert _cecid_components(2, 100)["hard_open"] is False


def test_adult_movement_does_not_require_soil_moisture():
    dry = _cecid_components(12, 100, wet=False)
    assert dry["emergence_score"] == 0.0
    assert dry["movement_score"] > 0.0


def _cecid_engine(target_state=TreeState.SUSCEPTIBLE, target_factor=1.0, stage=OrchardStage.FRUITLET):
    nodes = [
        TreeNode(0, "source", 122.58, 10.585, 0.0, 0.0, 2.5, TreeState.INFESTED),
        TreeNode(1, "target", 122.58005, 10.585, 5.0, 0.0, 2.5, target_state),
    ]
    nodes[1].treatment_susceptibility_factor = target_factor
    network = CecidHabitatNetwork.from_lonlat(
        source_positions={0: (nodes[0].lon, nodes[0].lat)},
        target_positions={1: (nodes[1].lon, nodes[1].lat)}, weed_zones=[],
    )
    weather = WeatherTimeSeries(pd.DataFrame({
        "datetime": pd.date_range("2026-04-01T12:00:00+08:00", periods=2, freq="h"),
        "wind_speed_ms": [1.0] * 2, "wind_dir_deg": [90.0] * 2,
        "temperature_c": [28.0] * 2, "rainfall_mm": [0.0] * 2,
        "cloud_cover_pct": [100.0] * 2,
        "daylight_condition": ["dim_overcast"] * 2,
    }), source="test")
    return TreeGraphEngine(
        graph=TreeGraph(nodes, max_dist=15.0), weather=weather,
        transition_mode="threshold", threshold=2.0,
        gates=[CecidFlyGate()], orchard_stage=OrchardStage.FRUITLET, pest_type="cecid",
        initial_rainfall_history=[0.0] * 68 + [2.0] * 4,
        stage_per_tree=[OrchardStage.FRUITLET, stage],
        cecid_source_pressures={0: 1.0}, cecid_habitat_network=network,
    )


def test_laying_capacity_is_spent_even_when_establishment_fails():
    exposed = _cecid_engine()
    protected = _cecid_engine(TreeState.BAGGED, target_factor=0.0)
    exposed.run(n_steps=2)
    protected.run(n_steps=2)
    exposed_capacity = exposed.cecid_cohort_model.lifecycle_diagnostics()["remaining_egg_capacity"]
    protected_capacity = protected.cecid_cohort_model.lifecycle_diagnostics()["remaining_egg_capacity"]
    assert 0.0 < exposed_capacity < 1.0
    assert protected_capacity == pytest.approx(exposed_capacity)
    assert protected.graph.nodes[1].risk == 0.0
    assert protected.graph.nodes[1].state == TreeState.BAGGED
    assert exposed.graph.nodes[1].state == TreeState.SUSCEPTIBLE


@pytest.mark.parametrize("state,stage", [
    (TreeState.DEAD, OrchardStage.FRUITLET),
    (TreeState.SUSCEPTIBLE, OrchardStage.MATURE),
])
def test_no_egg_capacity_is_spent_on_absent_host_fruit(state, stage):
    engine = _cecid_engine(state, stage=stage)
    engine.run(n_steps=2)
    assert engine.cecid_cohort_model.lifecycle_diagnostics()["remaining_egg_capacity"] == 1.0


def test_adult_expiry_preserves_existing_infested_fruit():
    engine = _cecid_engine(TreeState.INFESTED)
    engine.run(n_steps=1)
    for step in range(1, 49):
        engine.cecid_cohort_model.step(step, None, 0.0, False)
    assert engine.cecid_cohort_model.active_cohorts() == {}
    assert engine.graph.nodes[1].state == TreeState.INFESTED


def test_fruit_fly_uses_solar_daylight_and_continuous_temperature():
    gate = FruitFlyGate()
    gate.set_time_context("2026-04-01T07:00:00+08:00")
    assert gate.is_open(7, 1.0, 23.5, orchard_stage=OrchardStage.MATURE)
    assert gate.activity_components(7, 23.5)["activity_window"] == "daylight"
    assert 0 < gate.activity_components(7, 23.5)["temperature_score"] < 1
    assert not gate.is_open(7, 1.0, 23.5, orchard_stage=OrchardStage.FRUITLET)
    explicit = FruitFlyGate(temp_threshold_c=25.0)
    assert not explicit.is_open(7, 1.0, 23.5, orchard_stage=OrchardStage.MATURE)


def test_fruit_fly_dark_period_is_a_reduced_explicit_assumption():
    gate = FruitFlyGate()
    gate.set_time_context("2026-04-01T12:00:00+08:00")
    day = gate.activity_components(12, 28.0)
    gate.set_time_context("2026-04-01T02:00:00+08:00")
    night = gate.activity_components(2, 28.0)
    assert 0 < night["activity_score"] < day["activity_score"]
    assert night["night_activity_is_assumed"] is True


def test_manual_cloud_cover_reaches_engine_weather_and_diagnostics():
    request = SimulationRequest(
        pest_type="cecid", orchard_stage="fruitlet", hours=1,
        orchard_geojson={"type": "FeatureCollection", "features": []},
        manual_weather={"cloud_cover_pct": 100.0, "wind_speed_ms": 1.0, "daylight_condition": "dim_overcast"},
        manual_weather_start="2026-04-01T12:00:00+08:00",
    )
    records = build_weather_series(request)
    assert records[0]["cloud_cover_pct"] == 100.0
    frame = pd.DataFrame(records)
    frame["datetime"] = pd.to_datetime(frame["datetime"])
    weather = WeatherTimeSeries.from_dataframe(frame)
    assert weather.at(0)["cloud_cover_pct"] == 100.0
    diagnostic = compute_gate_diagnostics(records, "cecid", "fruitlet", initial_rainfall_history=[8.0])[0]
    assert diagnostic["activity_window"] == "cloudy_day"
    assert diagnostic["status"] == "favorable"
    with pytest.raises(ValueError):
        ManualWeather(cloud_cover_pct=101.0)


def test_missing_live_cloud_cover_stays_unknown():
    frame = pd.DataFrame([{
        "datetime": "2026-04-01T12:00:00+08:00", "wind_speed_ms": 1.0,
        "wind_dir_deg": 90.0, "temperature_c": 28.0, "rainfall_mm": 0.0,
    }])
    frame["datetime"] = pd.to_datetime(frame["datetime"])
    assert WeatherTimeSeries.from_dataframe(frame).at(0)["cloud_cover_pct"] is None


@pytest.mark.parametrize("mode", ["grid", "tree_graph"])
@pytest.mark.parametrize("temperature", [23.5, 28.0])
def test_both_engines_apply_the_assumed_day_and_night_weights(mode, temperature):
    def risk(hour):
        frame = pd.DataFrame([{
            "datetime": pd.Timestamp(f"2026-04-01T{hour:02d}:00:00+08:00"),
            "wind_speed_ms": 1.0, "wind_dir_deg": 90.0,
            "temperature_c": temperature, "rainfall_mm": 0.0,
        }])
        weather = WeatherTimeSeries(frame)
        if mode == "grid":
            grid = OrchardGrid(1, 2)
            grid.set_state(0, 0, CellState.INFESTED)
            grid.set_state(0, 1, CellState.UNBAGGED)
            engine = SimulationEngine(
                grid, weather, gates=[FruitFlyGate()], orchard_stage=OrchardStage.MATURE,
                transition_mode="threshold", threshold=2.0,
            )
            return engine.run(n_steps=1, progress=False).snapshots[0]["risk"][0, 1]
        graph = TreeGraph([
            TreeNode(0, "source", 122.58, 10.585, 0, 0, 2.5, TreeState.INFESTED),
            TreeNode(1, "target", 122.58005, 10.585, 5, 0, 2.5),
        ], max_dist=15)
        engine = TreeGraphEngine(graph, weather, transition_mode="threshold", threshold=2.0)
        return engine.run(n_steps=1).snapshots[0]["risks"][1]

    day, night = risk(12), risk(2)
    assert day > 0.0
    assert night == pytest.approx(day * 0.02)
