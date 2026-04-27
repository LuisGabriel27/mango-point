import pytest

from api.models.schemas import SimulationRequest
from api.routes.simulation import (
    _infer_weather_source,
    _tag_weather_source,
    _weather_source_from_data,
)
from api.services.weather_service import WeatherService


def _request(**kwargs):
    return SimulationRequest(
        pest_type="fruitfly",
        orchard_geojson={"type": "FeatureCollection", "features": []},
        **kwargs,
    )


def test_manual_weather_is_labeled_manual_and_tagged_without_mutation():
    raw_weather = [{
        "datetime": "2026-04-01T00:00:00Z",
        "hour": 0,
        "wind_speed_ms": 2.0,
        "wind_dir_deg": 90.0,
        "temperature_c": 30.0,
        "rainfall_mm": 0.0,
    }]
    request = _request(manual_weather={"temperature_c": 28.0})

    tagged = _tag_weather_source(raw_weather, "manual")

    assert raw_weather[0].get("source") is None
    assert tagged is not None
    assert tagged[0]["source"] == "manual"
    assert _infer_weather_source(request, tagged) == "manual"


def test_weather_source_uses_tagged_forecast_source():
    assert _weather_source_from_data(
        [{"source": "open-meteo"}],
        default="open-meteo",
    ) == "open-meteo"
    assert _weather_source_from_data(
        [{"source": "synthetic"}],
        default="open-meteo",
    ) == "synthetic"


def test_weather_source_defaults_to_open_meteo_for_legacy_untagged_forecast():
    request = _request()
    legacy_forecast = [{"temperature_c": 30.0}]

    assert _infer_weather_source(request, legacy_forecast) == "open-meteo"


def test_empty_weather_data_is_synthetic():
    request = _request()

    assert _infer_weather_source(request, []) == "synthetic"


def test_synthetic_forecast_entries_are_tagged():
    service = WeatherService()

    forecast = service._generate_synthetic_forecast(
        lat=10.79,
        lon=122.40,
        hours=3,
    )

    assert len(forecast) == 3
    assert {entry["source"] for entry in forecast} == {"synthetic"}


@pytest.mark.asyncio
async def test_get_forecast_fallback_preserves_synthetic_source(monkeypatch):
    service = WeatherService()

    async def fail_fetch(*args, **kwargs):
        raise RuntimeError("forced failure")

    monkeypatch.setattr(service, "_fetch_forecast_from_open_meteo", fail_fetch)

    forecast = await service.get_forecast(lat=10.79, lon=122.40, hours=2)

    assert len(forecast) == 2
    assert {entry["source"] for entry in forecast} == {"synthetic"}
