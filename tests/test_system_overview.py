from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from api.services.system_overview_service import (
    overview_queries, overview_window, summarize_overview,
)


NOW = datetime(2026, 10, 10, 16, 30, tzinfo=timezone.utc)  # Oct 11 in Manila


def empty_rows():
    return {name: [] for name in ("orchards", "runs", "observations", "alerts", "active_alerts")}


def orchard(uid="a", trees=100):
    return {"orchard_id": uid, "name": f"Orchard {uid}", "tree_count": trees,
            "is_active": True, "monitoring_enabled": True}


def run(bucket, orchard_id="a", pest="cecid", mode="grid", status="completed", count=1, version="v17"):
    return {"bucket": bucket, "orchard_id": orchard_id, "pest_type": pest,
            "simulation_mode": mode, "status": status, "count": count,
            "model_version": version, "weather_source": "manual"}


@pytest.mark.parametrize("period,start_date", [
    ("day", "2026-10-11"), ("week", "2026-10-05"),
    ("month", "2026-10-01"), ("year", "2026-01-01"),
])
def test_current_calendar_period_uses_philippine_date_and_stops_at_now(period, start_date):
    start, end = overview_window(period, NOW)
    assert end.date().isoformat() == "2026-10-11"
    assert end.utcoffset() == timedelta(hours=8)
    assert start.hour == start.minute == start.second == 0
    assert start.date().isoformat() == start_date
    assert end.astimezone(timezone.utc) == NOW


@pytest.mark.parametrize("period,chosen,first,last", [
    ("day", "2024-02-29", "2024-02-29", "2024-02-29"),
    ("week", "2024-02-29", "2024-02-26", "2024-03-03"),
    ("week", "2025-01-01", "2024-12-30", "2025-01-05"),
    ("month", "2024-02-29", "2024-02-01", "2024-02-29"),
    ("month", "2025-12-15", "2025-12-01", "2025-12-31"),
    ("year", "2024-02-29", "2024-01-01", "2024-12-31"),
])
def test_selected_calendar_ranges_cover_whole_periods_and_leap_dates(period, chosen, first, last):
    start, end = overview_window(period, NOW, date.fromisoformat(chosen))
    assert start.date().isoformat() == first
    assert end.date().isoformat() == last
    assert (start.hour, start.minute, start.second, start.microsecond) == (0, 0, 0, 0)
    assert (end.hour, end.minute, end.second, end.microsecond) == (23, 59, 59, 999999)
    assert start.utcoffset() == end.utcoffset() == timedelta(hours=8)


@pytest.mark.parametrize("period", ["day", "week", "month", "year"])
def test_future_dates_are_rejected_even_within_the_current_period(period):
    with pytest.raises(ValueError, match="today or an earlier date"):
        overview_window(period, NOW, date(2026, 10, 12))


def test_historical_month_fills_all_dates_without_using_period_end_as_refresh_time():
    chosen = date(2024, 2, 15)
    start, end = overview_window("month", NOW, chosen)
    result = summarize_overview("month", start, end, empty_rows(), selected_date=chosen, computed_at=NOW)
    assert result["selected_date"] == "2024-02-15"
    assert result["days"] == len(result["timeline"]) == 29
    assert result["timeline"][0]["date"] == "2024-02-01"
    assert result["timeline"][-1]["date"] == "2024-02-29"
    assert datetime.fromisoformat(result["computed_at"].replace("Z", "+00:00")) == NOW


def test_empty_period_keeps_current_inventory_and_older_active_alerts():
    start, end = overview_window("week", NOW)
    rows = empty_rows()
    rows["orchards"] = [orchard()]
    rows["active_alerts"] = [{"orchard_id": "a", "severity": "high", "count": 2}]
    result = summarize_overview("week", start, end, rows)
    assert len(result["timeline"]) == 7
    assert sum(day["simulations"] + day["observations"] + day["alerts"] for day in result["timeline"]) == 0
    assert result["inventory"]["trees"] == 100
    assert result["alerts"] == {"raised": 0, "active": 2, "high_critical_active": 2}
    assert result["orchard_activity"][0]["active_alerts"] == 2


def test_pests_engines_versions_and_repeat_inspections_are_separate_counts():
    start, end = overview_window("week", NOW)
    bucket = end.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    rows = empty_rows()
    rows["orchards"] = [orchard(), orchard("b", 25)]
    rows["runs"] = [run(bucket, count=3), run(bucket, mode="tree_graph", version="v16"),
                    run(bucket, pest="fruitfly", mode="tree_graph", version="v16"),
                    run(bucket, orchard_id="b", pest="fruitfly", count=2), run(bucket, status="failed")]
    rows["observations"] = [
        {"bucket": bucket, "orchard_id": "a", "pest_name": "Mango Cecid Fly", "presence": "present", "count": 2},
        {"bucket": bucket, "orchard_id": "a", "pest_name": "Mango Cecid Fly", "presence": "absent", "count": 4},
        {"bucket": bucket, "orchard_id": "a", "pest_name": "Mango Cecid Fly", "presence": "not_inspected", "count": 5},
        {"bucket": bucket, "orchard_id": "b", "pest_name": "Oriental Fruit Fly", "presence": "present", "count": 1},
    ]
    rows["alerts"] = [{"bucket": bucket, "orchard_id": "b", "count": 2}]
    result = summarize_overview("week", start, end, rows)
    assert result["inventory"]["trees"] == 125
    assert result["simulations"] == {"total": 8, "completed": 7, "failed": 1, "other": 0}
    assert result["observations"] == {"total": 12, "inspected": 7, "present": 3, "absent": 4, "not_inspected": 5}
    assert result["timeline"][-1] == {"date": "2026-10-11", "simulations": 7, "observations": 7, "present": 3, "alerts": 2}
    assert result["engines"] == {"grid": 5, "tree_graph": 2}
    assert result["model_versions"] == {"v17": 5, "v16": 2}
    assert result["weather_sources"] == {"manual": 7}
    assert result["pests"] == [
        {"pest_type": "cecid", "simulations": 4, "observations": 6, "present": 2},
        {"pest_type": "fruitfly", "simulations": 3, "observations": 1, "present": 1},
    ]
    assert sum(row["observations"] for row in result["orchard_activity"]) == 7
    assert sum(row["simulations"] for row in result["orchard_activity"]) == 7


def test_year_groups_calendar_months_and_retains_unassigned_and_archived_records():
    start, end = overview_window("year", NOW, date(2025, 10, 10))
    rows = empty_rows()
    rows["runs"] = [run(datetime(2025, 1, 1), orchard_id=None, version="Unrecorded"),
                    run(datetime(2025, 12, 1), orchard_id="archived")]
    result = summarize_overview("year", start, end, rows)
    assert len(result["timeline"]) == 12
    assert result["timeline"][0]["date"] == "2025-01-01"
    assert result["timeline"][-1]["date"] == "2025-12-01"
    assert result["timeline"][0]["simulations"] == 1
    assert result["timeline"][-1]["simulations"] == 1
    assert result["inventory"]["orchards"] == 0
    assert len(result["orchard_activity"]) == 2
    assert any(row["name"] == "Unassigned orchard" for row in result["orchard_activity"])
    assert result["model_versions"]["Unrecorded"] == 1
    assert result["orchards"][0]["orchard_id"] == "archived"


def test_scoped_inventory_leaves_complete_filter_directory_available():
    start, end = overview_window("month", NOW)
    rows = empty_rows()
    rows["orchards"] = [orchard(), orchard("b", 25)]
    result = summarize_overview("month", start, end, rows, "b")
    assert result["inventory"]["orchards"] == 1
    assert result["inventory"]["trees"] == 25
    assert len(result["orchards"]) == 2
    assert result["orchard_activity"][0]["orchard_id"] == "b"


def test_queries_scope_records_and_exclude_simulated_observations_without_history_limit():
    start, end = overview_window("week", NOW)
    sql = {key: str(query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
           for key, query in overview_queries("week", start, end, "orchard-b").items()}
    assert "infestation_record.simulation_id IS NULL" in sql["observations"]
    assert "orchard.orchard_uid = 'orchard-b'" in sql["observations"]
    for key in ("runs", "observations", "alerts"):
        assert ">= '2026-10-04 16:00:00'" in sql[key]
        assert "<= '2026-10-10 16:30:00'" in sql[key]
        assert "LIMIT" not in sql[key]
    assert "coalesce(infestation_record.record_date, infestation_record.created_at)" in sql["observations"]
    assert "simulation_run.orchard_id = 'orchard-b'" in sql["runs"]
    for key in ("alerts", "active_alerts"):
        assert "alert.orchard_id = 'orchard-b'" in sql[key]
    assert "alert.status = 'active'" in sql["active_alerts"]
    assert "triggered_at >=" not in sql["active_alerts"]
    assert "orchard-b" not in sql["orchards"]
    assert "response_payload" not in sql["runs"] and "output_geojson" not in sql["runs"]


def test_selected_day_queries_use_exact_philippine_midnight_boundaries_in_utc():
    start, end = overview_window("day", NOW, date(2024, 2, 29))
    queries = overview_queries("day", start, end)
    for key in ("runs", "observations", "alerts"):
        sql = str(queries[key].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        assert ">= '2024-02-28 16:00:00'" in sql
        assert "<= '2024-02-29 15:59:59.999999'" in sql


def test_endpoint_requires_auth_and_validates_filters(monkeypatch):
    from api.main import app
    from api.core.database import get_db
    from api.core.security import get_current_active_user
    from api.routes import monitoring

    summary = AsyncMock(return_value={"period": "month"})
    monkeypatch.setattr(monitoring, "get_system_overview", summary)
    monkeypatch.setattr(monitoring, "utcnow_aware", lambda: NOW)

    async def fake_db():
        yield object()

    app.dependency_overrides[get_db] = fake_db
    try:
        client = TestClient(app)
        assert client.get("/monitoring/overview").status_code == 401
        summary.assert_not_awaited()
        app.dependency_overrides[get_current_active_user] = lambda: object()
        assert client.get("/monitoring/overview?period=decade").status_code == 422
        assert client.get("/monitoring/overview?orchard_id=").status_code == 422
        for invalid in ("2024-02-30", "2026-10-12", "2024-02", "invalid", ""):
            assert client.get(f"/monitoring/overview?date={invalid}").status_code == 422
        summary.assert_not_awaited()
        for period in ("day", "week", "month", "year"):
            response = client.get(f"/monitoring/overview?period={period}&date=2024-02-29&orchard_id=b")
            assert response.status_code == 200
            assert summary.await_args.args[1:] == (period, "b")
            assert summary.await_args.kwargs == {"selected_date": date(2024, 2, 29)}
        response = client.get("/monitoring/overview?period=month&orchard_id=b")
        assert response.status_code == 200
        assert response.json() == {"period": "month"}
        assert summary.await_args.args[1:] == ("month", "b")
        assert summary.await_args.kwargs == {"selected_date": None}
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_active_user, None)


def test_storage_failure_returns_error_instead_of_empty_success(monkeypatch):
    from api.main import app
    from api.core.database import get_db
    from api.core.security import get_current_active_user
    from api.routes import monitoring

    monkeypatch.setattr(monitoring, "get_system_overview", AsyncMock(side_effect=ConnectionError("offline")))
    app.dependency_overrides[get_db] = lambda: object()
    app.dependency_overrides[get_current_active_user] = lambda: object()
    try:
        response = TestClient(app, raise_server_exceptions=False).get("/monitoring/overview")
        assert response.status_code == 503
        assert "temporarily unavailable" in response.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_active_user, None)
