"""Bright cloudy skies, dim overcast, custom light and rain-break regressions."""

import asyncio
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from api.models.schemas import ManualWeather, ManualWeatherBlock, ManualWeatherEntry, SimulationRequest
from api.services.simulation_service import SimulationService
from api.services.weather_service import WeatherService
from api.services.alert_service import AlertService
from tests.test_cecid_moisture_emergence import _engine, _target_risk, _weather
from utils.daylight import daylight_light_components
from utils.solar import MANILA_TZ, clear_sky_shortwave_reference
from utils.weather import WeatherTimeSeries
from utils.weather_builder import build_weather_series, compute_gate_diagnostics

NOON = datetime(2026, 4, 1, 12, tzinfo=MANILA_TZ)


def _light_weather(**changes):
    return {**_weather()[0], **changes}


def _replace_weather(engine, entries):
    frame = pd.DataFrame(entries)
    frame["datetime"] = pd.to_datetime(frame["datetime"])
    engine.weather = WeatherTimeSeries(frame)
    return engine


@pytest.mark.parametrize("mode", ["grid", "tree_graph"])
@pytest.mark.parametrize("changes,enabled", [
    ({"shortwave_radiation_wm2": 900, "direct_normal_irradiance_wm2": 750}, False),
    ({"shortwave_radiation_wm2": 100, "direct_normal_irradiance_wm2": 750}, False),
    ({"shortwave_radiation_wm2": 900, "direct_normal_irradiance_wm2": 0}, False),
    ({"shortwave_radiation_wm2": 100, "direct_normal_irradiance_wm2": 0}, True),
    ({"shortwave_radiation_wm2": None, "direct_normal_irradiance_wm2": None}, False),
    ({"shortwave_radiation_wm2": None}, False),
    ({"cloud_cover_pct": 1}, False),
    ({"cloud_cover_pct": None}, False),
    ({"daylight_condition": "bright_sunshine"}, False),
    ({"daylight_condition": "dim_overcast", "shortwave_radiation_wm2": None, "direct_normal_irradiance_wm2": None}, True),
])
def test_both_engines_require_supported_daylight_for_emergence_and_movement(mode, changes, enabled):
    entry = _light_weather(**changes)
    engine = _replace_weather(_engine(mode), [entry])
    assert bool(_target_risk(engine, mode) > 0) is enabled
    assert len(engine.cecid_cohort_events) == int(enabled)
    diagnostic = engine.cecid_habitat_diagnostics[0]
    gate_diagnostic = compute_gate_diagnostics([entry], "cecid", "fruitlet", cecid_initial_soil_moisture_score=1)[0]
    assert diagnostic["eligible"] is enabled
    assert gate_diagnostic["emergence_available"] is enabled
    assert gate_diagnostic["movement_available"] is enabled
    assert diagnostic["movement_score"] == pytest.approx(gate_diagnostic["movement_score"])
    assert diagnostic["daylight_light_basis"] == gate_diagnostic["daylight_light_basis"]
    assert diagnostic["canopy_shade_enables_activity"] is False


@pytest.mark.parametrize("hour", [8, 12, 16])
def test_low_sun_is_normalized_instead_of_treated_as_overcast(hour):
    timestamp = NOON.replace(hour=hour)
    reference = clear_sky_shortwave_reference(timestamp, 10.585, 122.58)
    light = daylight_light_components({"cloud_cover_pct": 100,
        "shortwave_radiation_wm2": reference * 0.95, "direct_normal_irradiance_wm2": 0}, timestamp, 10.585, 122.58)
    assert light["daylight_light_score"] == 0
    assert light["daylight_brightness_ratio"] == pytest.approx(0.95)
    assert 0 < reference < 1100
    assert clear_sky_shortwave_reference(timestamp.astimezone(timezone.utc), 10.585, 122.58) == reference


@pytest.mark.parametrize("mode", ["grid", "tree_graph"])
def test_canopy_shade_does_not_enable_daytime_activity(mode):
    entry = _light_weather(cloud_cover_pct=0, shortwave_radiation_wm2=None, direct_normal_irradiance_wm2=None,
                          canopy_shade=True, tree_shade_pct=100, daylight_condition="tree_shade")
    engine = _replace_weather(_engine(mode), [entry])
    assert _target_risk(engine, mode) == 0
    assert engine.cecid_cohort_events == []


@pytest.mark.parametrize("mode", ["grid", "tree_graph"])
def test_dim_scenario_cannot_bypass_darkness_rain_dry_soil_or_wrong_stage(mode):
    for changes, score in [
        ({"datetime": "2026-04-01T02:00:00+08:00", "hour": 2}, 1),
        ({"rainfall_mm": 2}, 1),
        ({}, 0),
    ]:
        engine = _replace_weather(_engine(mode, score=score), [_light_weather(daylight_condition="dim_overcast", **changes)])
        assert _target_risk(engine, mode) == 0
        assert engine.cecid_cohort_events == []
    entry = _light_weather(daylight_condition="dim_overcast")
    diagnostic = compute_gate_diagnostics([entry], "cecid", "mature", cecid_initial_soil_moisture_score=1)[0]
    assert not diagnostic["emergence_available"] and not diagnostic["movement_available"]


@pytest.mark.parametrize("mode", ["grid", "tree_graph"])
def test_rain_four_hours_then_dim_one_hour_break_emerges_and_survivors_resume(mode):
    entries = [
        _light_weather(datetime=(NOON.replace(hour=8) + timedelta(hours=index)).isoformat(),
                       hour=8 + index, rainfall_mm=rain)
        for index, rain in enumerate([2, 2, 2, 2, 0, 2, 2, 0])
    ]
    engine = _replace_weather(_engine(mode, score=None), entries)
    engine.run(n_steps=8, progress=False)
    assert [event["timestep"] for event in engine.cecid_cohort_events] == [4]
    assert [item["eligible"] for item in engine.cecid_habitat_diagnostics] == [False]*4 + [True, False, False, True]
    assert all(item["active_laying_cohort_count"] == 1 for item in engine.cecid_habitat_diagnostics[4:])


@pytest.mark.parametrize("mode", ["grid", "tree_graph"])
def test_bright_first_hour_keeps_soil_batch_until_dim_hour(mode):
    bright = _light_weather(shortwave_radiation_wm2=900, direct_normal_irradiance_wm2=750)
    dim = _light_weather(datetime="2026-04-01T13:00:00+08:00", hour=13)
    engine = _replace_weather(_engine(mode), [bright, dim])
    engine.run(n_steps=2, progress=False)
    assert [event["timestep"] for event in engine.cecid_cohort_events] == [1]
    assert engine.cecid_habitat_diagnostics[0]["remaining_soil_batches"] == 1


@pytest.mark.parametrize("kind", ["constant", "blocks", "series"])
def test_custom_light_survives_building_and_request_replay(kind):
    values = {"cloud_cover_pct": 100, "daylight_condition": "bright_sunshine", "daylight_condition_basis": "observed"}
    fields = {"constant": {"manual_weather": values},
              "blocks": {"manual_weather_blocks": [{"start_hour": 0, "end_hour": 2, **values}]},
              "series": {"manual_weather_series": [values, {}]}}[kind]
    request = SimulationRequest(pest_type="cecid", orchard_stage="fruitlet", hours=2,
        orchard_geojson={"type": "FeatureCollection", "features": []},
        manual_weather_start=NOON, **fields)
    records = build_weather_series(request)
    assert all(record["daylight_condition"] == "bright_sunshine" for record in records)
    assert all(record["daylight_condition_basis"] == "observed" for record in records)
    assert build_weather_series(SimulationRequest.model_validate(request.model_dump(mode="json"))) == records
    assert all(item["daylight_light_basis"] == "custom_observed" and not item["movement_available"]
               for item in compute_gate_diagnostics(records, "cecid", "fruitlet", cecid_initial_soil_moisture_score=1))


@pytest.mark.parametrize("schema", [ManualWeather, ManualWeatherEntry, ManualWeatherBlock])
@pytest.mark.parametrize("invalid", [
    {"daylight_condition": "tree_shade"}, {"daylight_condition_basis": "measured"},
    {"shortwave_radiation_wm2": -1}, {"direct_normal_irradiance_wm2": float("nan")},
])
def test_custom_light_rejects_unrecognized_conditions_and_invalid_radiation(schema, invalid):
    fields = {"start_hour": 0, "end_hour": 1} if schema is ManualWeatherBlock else {}
    with pytest.raises(ValueError):
        schema(**fields, **invalid)


def test_provider_radiation_mapping_preserves_zero_and_unknown():
    hourly = {"time": ["2026-04-01T12:00", "2026-04-01T13:00"],
        "cloud_cover": [100, 100], "shortwave_radiation_instant": [100, None],
        "direct_normal_irradiance_instant": [0, float("nan")]}
    records = WeatherService._records_from_hourly(hourly, "open-meteo")
    assert records[0]["direct_normal_irradiance_wm2"] == 0
    assert records[0]["shortwave_radiation_wm2"] == 100
    assert records[1]["shortwave_radiation_wm2"] is None
    assert records[1]["direct_normal_irradiance_wm2"] is None


def test_frontend_and_backend_light_rules_match_across_dates_and_sun_angles():
    cases = []
    for month, hour in [(4, 8), (4, 12), (4, 16), (12, 12), (2, 12)]:
        timestamp = NOON.replace(month=month, hour=hour)
        for ghi, dni, cloud in [(900, 750, 100), (100, 0, 100), (400, 300, 65), (100, 0, 1)]:
            cases.append({"datetime": timestamp.isoformat(), "weather": {
                "cloud_cover_pct": cloud, "shortwave_radiation_wm2": ghi, "direct_normal_irradiance_wm2": dni}})
    script = "import {daylightLightComponents} from './frontend/src/utils/daylightLight.js'; let input=''; for await (const chunk of process.stdin) input+=chunk; process.stdout.write(JSON.stringify(JSON.parse(input).map(c=>daylightLightComponents(c.weather,new Date(c.datetime)))));"
    completed = subprocess.run(["node", "--input-type=module", "-e", script], input=json.dumps(cases), text=True,
                               capture_output=True, check=True, cwd=Path(__file__).resolve().parents[1])
    for case, frontend in zip(cases, json.loads(completed.stdout)):
        backend = daylight_light_components(case["weather"], datetime.fromisoformat(case["datetime"]), 10.585, 122.58)
        assert frontend["daylight_light_score"] == pytest.approx(backend["daylight_light_score"])
        assert frontend["clear_sky_shortwave_reference_wm2"] == pytest.approx(backend["clear_sky_shortwave_reference_wm2"])
        assert frontend["daylight_light_status"] == backend["daylight_light_status"]


@pytest.mark.parametrize("mode", ["grid", "tree_graph"])
@pytest.mark.parametrize("condition,enabled", [("bright_sunshine", False), ("dim_overcast", True)])
def test_service_saves_custom_light_and_replays_the_same_result(mode, condition, enabled):
    orchard = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [122.58 + i * 0.000045, 10.585]},
         "properties": {"Tree_ID": str(i), "Status": "infected" if i == 0 else "healthy"}}
        for i in range(2)
    ]}
    request = SimulationRequest(pest_type="cecid", orchard_stage="fruitlet", simulation_mode=mode,
        orchard_geojson=orchard, hours=1, random_seed=42, include_time_series=True,
        manual_weather_start=NOON, manual_soil_context={"preset": "moist"},
        manual_weather={"cloud_cover_pct": 100, "wind_speed_ms": 1,
                        "daylight_condition": condition, "daylight_condition_basis": "observed"})
    service = SimulationService()
    first = asyncio.run(service.run_simulation(request, build_weather_series(request)))
    restored = SimulationRequest.model_validate(request.model_dump(mode="json"))
    replay = asyncio.run(service.run_simulation(restored, build_weather_series(restored)))
    assert first.risk_geojson == replay.risk_geojson
    assert len(first.metadata.cecid_cohort_events) == int(enabled)
    assumptions = first.metadata.cecid_source_assumptions
    assert assumptions["cloud_cover_alone_enables_activity"] is False
    assert assumptions["canopy_shade_enables_activity"] is False
    assert assumptions["light_response_is_calibrated"] is False
    assert first.metadata.cecid_habitat_diagnostics[0]["daylight_light_basis"] == "custom_observed"
    assert first.time_series[0].weather["daylight_condition"] == condition
    assert first.time_series[0].weather["daylight_condition_basis"] == "observed"
    assert first.time_series[0].weather["cloud_cover_pct"] == 100


def test_daytime_live_alert_rejects_bright_clouds_and_exposes_dim_light_evidence():
    service = AlertService()
    arguments = {"orchard_id": "light-test", "lat": 10.585, "lon": 122.58,
        "orchard_stage": "fruitlet", "monitored_pest_types": ["cecid"],
        "antecedent": [{"rainfall_mm": 8}], "provenance": {"source": "open-meteo", "provider": "open-meteo"}}
    bright = _light_weather(source="open-meteo", shortwave_radiation_wm2=900, direct_normal_irradiance_wm2=750)
    assert service.check_weather_forecast_alerts(forecast=[bright], **arguments) == []
    dim = _light_weather(source="open-meteo")
    alerts = service.check_weather_forecast_alerts(forecast=[dim], **arguments)
    assert len(alerts) == 1
    context = alerts[0].suggested_simulation_params["cecid_forecast_context"]
    assert context["daylight_light_basis"] == "radiation_estimate"
    assert context["direct_normal_irradiance_wm2"] == 0


@pytest.mark.asyncio
async def test_current_weather_requests_and_preserves_instant_sunlight(monkeypatch):
    captured = {}
    class Response:
        def raise_for_status(self):
            pass
        def json(self):
            return {"current": {"time": "2026-04-01T12:00", "cloud_cover": 100,
                                "shortwave_radiation_instant": 100, "direct_normal_irradiance_instant": 0}}
    class Client:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, url, params):
            captured.update(params)
            return Response()
    monkeypatch.setattr("api.services.weather_service.httpx.AsyncClient", Client)
    record = await WeatherService()._fetch_current_v2(10.585, 122.58, NOON)
    assert "shortwave_radiation_instant" in captured["current"].split(",")
    assert "direct_normal_irradiance_instant" in captured["current"].split(",")
    assert record["shortwave_radiation_wm2"] == 100
    assert record["direct_normal_irradiance_wm2"] == 0
