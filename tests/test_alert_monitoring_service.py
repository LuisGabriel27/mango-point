from types import SimpleNamespace

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

    async def fake_forecast(lat, lon, hours):
        return [
            {
                "datetime": "2026-04-28T09:00:00Z",
                "hour": 9,
                "wind_speed_ms": 2.0,
                "wind_dir_deg": 90.0,
                "temperature_c": 30.0,
                "humidity": 75.0,
                "rainfall_mm": 0.0,
            }
        ]

    monkeypatch.setattr(
        "api.services.alert_monitoring_service.weather_service.get_forecast",
        fake_forecast,
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

    async def fake_forecast(lat, lon, hours):
        return [
            {
                "datetime": "2026-04-28T09:00:00Z",
                "hour": 9,
                "wind_speed_ms": 2.0,
                "wind_dir_deg": 90.0,
                "temperature_c": 20.0,
                "humidity": 75.0,
                "rainfall_mm": 0.0,
            }
        ]

    monkeypatch.setattr(
        "api.services.alert_monitoring_service.weather_service.get_forecast",
        fake_forecast,
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
