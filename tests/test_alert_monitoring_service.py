from types import SimpleNamespace
from datetime import datetime, timedelta

import pytest

from api.services.alert_monitoring_service import AlertMonitoringService


class _FakeDb:
    def __init__(self):
        self.added = []
        self.flushed = 0

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        self.flushed += 1


def _orchard(**kwargs):
    values = {
        "orchard_id": 1,
        "orchard_uid": "orchard-a",
        "name": "Orchard A",
        "centroid_lon": 122.0,
        "centroid_lat": 10.0,
        "geojson": None,
        "monitored_pest_types": ["fruitfly"],
        "orchard_stage": "mature",
        "days_since_flowering": 60,
        "last_monitoring_scan_at": None,
    }
    values.update(kwargs)
    return SimpleNamespace(**values)


def test_alert_monitoring_helpers_normalize_pests_and_sugar_index():
    service = AlertMonitoringService()

    assert service._monitored_pest_types(["fruitfly", "cecid", "unknown"]) == [
        "fruitfly",
        "cecid",
    ]
    assert service._monitored_pest_types("cecid, fruitfly") == ["cecid", "fruitfly"]
    assert service._monitored_pest_types([]) == ["cecid", "fruitfly"]
    assert service._sugar_index_from_days(60) == 1.0
    assert service._sugar_index_from_days(0) == 0.3


@pytest.mark.asyncio
async def test_scan_orchard_creates_gate_condition_alert(monkeypatch):
    service = AlertMonitoringService()
    db = _FakeDb()

    async def fake_forecast_bundle(lat, lon, hours):
        return {"antecedent": [], "provenance": {"source": "test"}, "forecast": [
            {
                "datetime": "2026-04-28T09:00:00+08:00",
                "hour": 9,
                "wind_speed_ms": 2.0,
                "wind_dir_deg": 90.0,
                "temperature_c": 30.0,
                "humidity": 75.0,
                "rainfall_mm": 0.0,
            }
        ]}

    monkeypatch.setattr(
        "api.services.alert_monitoring_service.weather_service.get_forecast_bundle",
        fake_forecast_bundle,
    )

    summary = await service.scan_orchard(
        db=db,
        orchard=_orchard(),
        hours=1,
        send_notifications=False,
        dedupe_hours=0,
    )

    assert summary["alerts_created"] == 1
    assert summary["gate_open"]["fruitfly"] == 1
    assert len(db.added) == 1
    assert db.added[0].orchard_id == "orchard-a"
    assert db.added[0].zone_name == "Fruit fly gate condition"


@pytest.mark.asyncio
async def test_scan_orchard_updates_timestamp_without_alert_when_gate_closed(monkeypatch):
    service = AlertMonitoringService()
    db = _FakeDb()
    orchard = _orchard(orchard_stage="fruitlet")

    async def fake_forecast_bundle(lat, lon, hours):
        return {"antecedent": [], "provenance": {"source": "test"}, "forecast": [
            {
                "datetime": "2026-04-28T09:00:00+08:00",
                "hour": 9,
                "wind_speed_ms": 2.0,
                "wind_dir_deg": 90.0,
                "temperature_c": 20.0,
                "humidity": 75.0,
                "rainfall_mm": 0.0,
            }
        ]}

    monkeypatch.setattr(
        "api.services.alert_monitoring_service.weather_service.get_forecast_bundle",
        fake_forecast_bundle,
    )

    summary = await service.scan_orchard(
        db=db,
        orchard=orchard,
        hours=1,
        send_notifications=False,
        dedupe_hours=0,
    )

    assert summary["alerts_created"] == 0
    assert db.added == []
    assert orchard.last_monitoring_scan_at is not None


@pytest.mark.asyncio
async def test_scan_orchard_creates_actionable_cecid_live_forecast_alert(monkeypatch):
    service = AlertMonitoringService()
    db = _FakeDb()
    orchard = _orchard(
        orchard_stage="fruitlet",
        monitored_pest_types=["cecid"],
        centroid_lon=122.58,
        centroid_lat=10.585,
    )
    start = datetime.fromisoformat("2026-04-28T05:00:00+08:00")

    async def fake_forecast_bundle(lat, lon, hours):
        return {
            "antecedent": [
                {"rainfall_mm": 2.0 if 56 <= step < 60 else 0.0}
                for step in range(72)
            ],
            "provenance": {
                "provider": "open-meteo",
                "source": "open-meteo",
                "timezone": "Asia/Manila",
            },
            "forecast": [
                {
                    "datetime": (start + timedelta(hours=step)).isoformat(),
                    "hour": (start + timedelta(hours=step)).hour,
                    "wind_speed_ms": 1.0,
                    "wind_dir_deg": 90.0,
                    "temperature_c": 27.0,
                    "humidity": 85.0,
                    "rainfall_mm": 0.0,
                }
                for step in range(hours)
            ],
        }

    monkeypatch.setattr(
        "api.services.alert_monitoring_service.weather_service.get_forecast_bundle",
        fake_forecast_bundle,
    )

    summary = await service.scan_orchard(
        db=db,
        orchard=orchard,
        hours=8,
        send_notifications=False,
        dedupe_hours=0,
    )

    assert summary["alerts_created"] == 1
    assert summary["operational_weather"] is True
    assert summary["forecast_assessment"]["cecid"]["favorable_hours"] == 2
    assert len(db.added) == 1
    alert = db.added[0]
    assert alert.zone_name == "Cecid fly weather forecast"
    assert alert.suggested_simulation_params["weather_mode"] == "live"
    assert alert.suggested_simulation_params["auto_run"] is False
