"""Q3: existing soil moisture controls emergence without a rain-arming gate."""

import asyncio
from collections import deque

import numpy as np
import pandas as pd
import pytest

from api.models.schemas import SimulationRequest
from api.services.simulation_service import SimulationService
from core.biological_rules import CecidFlyGate, CecidSourceCohortModel
from core.cecid_habitat import CecidHabitatNetwork
from core.config import CellState, OrchardStage
from core.grid import OrchardGrid
from core.simulation_engine import SimulationEngine
from core.tree_graph_model import TreeGraph, TreeGraphEngine, TreeNode, TreeState
from utils.weather import WeatherTimeSeries
from utils.weather_builder import (
    build_manual_antecedent_weather, compute_gate_diagnostics, resolve_initial_soil_moisture,
)


def _weather(rain=0.0):
    return [{
        "datetime": "2026-04-01T12:00:00+08:00", "hour": 12,
        "temperature_c": 28.0, "wind_speed_ms": 1.0, "wind_dir_deg": 90.0,
        "rainfall_mm": rain, "cloud_cover_pct": 100.0,
        "shortwave_radiation_wm2": 100.0, "direct_normal_irradiance_wm2": 0.0,
    }]


def _engine(mode, score=1.0, rain=0.0, sources=True, antecedent=None):
    frame = pd.DataFrame(_weather(rain))
    frame["datetime"] = pd.to_datetime(frame["datetime"])
    weather = WeatherTimeSeries(frame)
    gate = CecidFlyGate(initial_soil_moisture_score=score)
    positions = [(122.58, 10.585), (122.580045, 10.585)]
    history = [entry["rainfall_mm"] for entry in antecedent] if antecedent else [0.0] * 72
    if mode == "grid":
        grid = OrchardGrid(1, 2)
        grid.set_state(0, 0, CellState.INFESTED)
        grid.set_state(0, 1, CellState.UNBAGGED)
        source_map = {(0, 0): 1.0} if sources else {}
        network = CecidHabitatNetwork.from_lonlat(
            {(0, 0): positions[0]} if sources else {}, {(0, 1): positions[1]}, [],
        )
        return SimulationEngine(
            grid, weather, gates=[gate], orchard_stage=OrchardStage.FRUITLET,
            transition_mode="threshold", threshold=2.0,
            initial_rainfall_history=history, cecid_antecedent_weather=antecedent,
            cecid_source_pressures=source_map, cecid_habitat_network=network,
        )
    nodes = [
        TreeNode(0, "source", *positions[0], 0, 0, 2.5, TreeState.INFESTED),
        TreeNode(1, "target", *positions[1], 5, 0, 2.5),
    ]
    network = CecidHabitatNetwork.from_lonlat(
        {0: positions[0]} if sources else {}, {1: positions[1]}, [],
    )
    return TreeGraphEngine(
        TreeGraph(nodes, max_dist=15), weather, gates=[gate], pest_type="cecid",
        orchard_stage=OrchardStage.FRUITLET, transition_mode="threshold", threshold=2.0,
        initial_rainfall_history=history, cecid_antecedent_weather=antecedent,
        cecid_source_pressures={0: 1.0} if sources else {}, cecid_habitat_network=network,
    )


def _target_risk(engine, mode):
    result = engine.run(n_steps=1, progress=False)
    return result.snapshots[0]["risk"][0, 1] if mode == "grid" else result.snapshots[0]["risks"][1]


@pytest.mark.parametrize("mode", ["grid", "tree_graph"])
def test_moist_soil_emerges_without_recorded_rain(mode):
    engine = _engine(mode)
    assert _target_risk(engine, mode) > 0
    assert len(engine.cecid_cohort_events) == 1
    assert engine.cecid_cohort_events[0]["timestep"] == 0


@pytest.mark.parametrize("mode", ["grid", "tree_graph"])
def test_light_rain_modulates_emergence_instead_of_requiring_a_dry_hour(mode):
    dry = _engine(mode)
    drizzle = _engine(mode, rain=0.5)
    dry_risk, drizzle_risk = _target_risk(dry, mode), _target_risk(drizzle, mode)
    assert 0 < drizzle_risk < dry_risk
    assert len(drizzle.cecid_cohort_events) == 1


@pytest.mark.parametrize("mode", ["grid", "tree_graph"])
@pytest.mark.parametrize("score,rain,sources", [(0.0, 0.0, True), (None, 0.0, True), (1.0, 1.0, True), (1.0, 0.0, False)])
def test_moisture_does_not_bypass_dry_soil_heavy_rain_or_missing_insects(mode, score, rain, sources):
    engine = _engine(mode, score=score, rain=rain, sources=sources)
    assert _target_risk(engine, mode) == 0.0
    assert engine.cecid_cohort_events == []


@pytest.mark.parametrize("mode", ["grid", "tree_graph"])
def test_initial_moisture_is_not_backdated_into_antecedent_replay(mode):
    antecedent = [{**_weather()[0], "datetime": "2026-03-31T12:00:00+08:00"}]
    engine = _engine(mode, antecedent=antecedent)
    assert engine.cecid_cohort_events == []
    assert _target_risk(engine, mode) > 0
    assert engine.cecid_cohort_events[0]["antecedent"] is False


def test_grid_final_state_path_uses_the_same_moisture_and_cohort_state():
    recorded = _engine("grid")
    fast = _engine("grid")
    recorded.run(n_steps=1, progress=False)
    final = fast.run_final_state(n_steps=1)
    np.testing.assert_allclose(final.risk, recorded.grid.risk)
    assert fast.cecid_cohort_events == recorded.cecid_cohort_events


def test_explicit_hour_zero_moisture_decays_and_receives_only_forecast_rain():
    gate = CecidFlyGate(initial_soil_moisture_score=0.8)
    history = deque([100.0] * 71 + [0.0], maxlen=72)
    gate.set_simulation_step(0)
    assert gate.soil_wetness(history) == pytest.approx(4.0)
    history.append(2.0)
    gate.set_simulation_step(1)
    assert gate.soil_wetness(history) == pytest.approx(4.0 * 2 ** (-1 / 48) + 2.0)
    gate.set_simulation_step(48)
    assert gate.soil_wetness(deque([0.0] * 72)) == pytest.approx(2.0)
    gate.set_simulation_step(-1)
    assert gate.soil_wetness(deque([0.0] * 72)) == 0.0


def test_emergence_gate_does_not_have_an_independent_rain_arming_requirement():
    model = CecidSourceCohortModel({"soil": 1.0})
    assert model.step(0, None, 0.0, True)["soil"] == 1.0
    for step in range(1, 51):
        model.step(step, None, 2.0 if step % 2 else 0.0, True)
    assert len(model.events) == 1
    assert model.active_cohorts() == {}


@pytest.mark.parametrize("mode", ["grid", "tree_graph"])
@pytest.mark.parametrize("scenario", ["custom", "live"])
def test_service_preserves_initial_moisture_and_replays_in_both_weather_modes(mode, scenario):
    orchard = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [122.58 + i * 0.000045, 10.585]},
         "properties": {"Tree_ID": str(i), "Status": "infected" if i == 0 else "healthy"}}
        for i in range(2)
    ]}
    fields = ({"manual_soil_context": {"preset": "moist", "initial_moisture_score": 0.8},
               "manual_weather": {"cloud_cover_pct": 100.0},
               "manual_weather_start": "2026-04-01T12:00:00+08:00"}
              if scenario == "custom" else {"cecid_initial_soil_moisture_score": 0.8})
    request = SimulationRequest(
        pest_type="cecid", orchard_stage="fruitlet", simulation_mode=mode,
        orchard_geojson=orchard, hours=1, random_seed=42, **fields,
    )
    context = build_manual_antecedent_weather(request) or []
    assert all(entry["rainfall_mm"] == 0 for entry in context)
    first = asyncio.run(SimulationService().run_simulation(request, _weather(), weather_context=context))
    replay = asyncio.run(SimulationService().run_simulation(
        SimulationRequest.model_validate(request.model_dump(mode="json")), _weather(), weather_context=context,
    ))
    assumptions = first.metadata.cecid_source_assumptions
    assert assumptions["initial_soil_moisture_score"] == 0.8
    assert assumptions["soil_emergence_requires_new_rain"] is False
    assert len(first.metadata.cecid_cohort_events) == 1
    assert first.metadata.cecid_cohort_events[0]["antecedent"] is False
    assert first.risk_geojson == replay.risk_geojson
    diagnostic = compute_gate_diagnostics(
        _weather(), "cecid", "fruitlet", cecid_initial_soil_moisture_score=resolve_initial_soil_moisture(request),
    )[0]
    assert diagnostic["moisture_score"] == pytest.approx(0.8)
    assert diagnostic["emergence_available"] is True


def test_explicit_score_overrides_preset_and_rejects_invalid_values():
    base = {"pest_type": "cecid", "orchard_geojson": {"type": "FeatureCollection", "features": []}}
    request = SimulationRequest(**base, manual_soil_context={"preset": "moist"}, cecid_initial_soil_moisture_score=0.0)
    assert resolve_initial_soil_moisture(request) == 0.0
    for value in (-0.1, 1.1, float("nan")):
        with pytest.raises(ValueError):
            SimulationRequest(**base, cecid_initial_soil_moisture_score=value)
