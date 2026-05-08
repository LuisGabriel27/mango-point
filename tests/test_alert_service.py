from types import SimpleNamespace

import numpy as np
import pytest

from api.routes import alerts as alerts_route
from api.routes import simulation as simulation_route
from api.models.schemas import (
    AlertActionStatusEnum,
    AlertActionUpdate,
    AlertCreate,
    AlertSeverityEnum,
)
from api.services.alert_service import AlertService, alert_service


def _tree_feature(tree_id, risk, state="unbagged", lon=122.0, lat=10.0):
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "tree_id": tree_id,
            "risk": risk,
            "state": state,
        },
    }


def test_tree_feature_alerts_use_tree_ids_and_centroid():
    service = AlertService()
    service.risk_threshold = 0.75

    alerts = service.check_tree_feature_alerts(
        features=[
            _tree_feature("10", 0.90, lon=122.0, lat=10.0),
            _tree_feature("11", 0.98, state="bagged", lon=140.0, lat=20.0),
            _tree_feature("12", 0.96, lon=124.0, lat=12.0),
            _tree_feature("13", 0.50, lon=130.0, lat=30.0),
        ],
        orchard_id="orchard-a",
        simulation_run_id="run-1",
    )

    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.severity == AlertSeverityEnum.CRITICAL
    assert alert.risk_value == 0.96
    assert alert.affected_cells == []
    assert alert.affected_tree_ids == ["10", "12"]
    assert alert.centroid_lon == 123.0
    assert alert.centroid_lat == 11.0
    assert alert.simulation_run_id == "run-1"


def test_tree_feature_alerts_ignore_protected_and_terminal_states():
    service = AlertService()
    service.risk_threshold = 0.75

    alerts = service.check_tree_feature_alerts(
        features=[
            _tree_feature("20", 0.99, state="bagged"),
            _tree_feature("21", 0.99, state="infested"),
            _tree_feature("22", 0.99, state="dead"),
        ],
        orchard_id="orchard-a",
    )

    assert alerts == []


def test_tree_feature_alerts_classify_medium_single_tree_risk():
    service = AlertService()
    service.risk_threshold = 0.75

    alerts = service.check_tree_feature_alerts(
        features=[_tree_feature("30", 0.80)],
        orchard_id="orchard-a",
    )

    assert len(alerts) == 1
    assert alerts[0].severity == AlertSeverityEnum.MEDIUM


def test_tree_feature_alerts_can_use_simulation_threshold_override():
    service = AlertService()
    service.risk_threshold = 0.75

    assert service.check_tree_feature_alerts(
        features=[_tree_feature("40", 0.60)],
        orchard_id="orchard-a",
    ) == []

    alerts = service.check_tree_feature_alerts(
        features=[_tree_feature("40", 0.60)],
        orchard_id="orchard-a",
        risk_threshold=0.50,
    )

    assert len(alerts) == 1
    assert alerts[0].risk_value == 0.60
    assert "Alert threshold: 50%" in alerts[0].message


def test_grid_alerts_use_threshold_override_and_cell_centroid():
    service = AlertService()
    service.risk_threshold = 0.75

    risk_grid = np.array([[0.1, 0.6], [0.2, 0.4]])
    state_grid = np.array([[1, 1], [1, 2]])
    tree_ids = np.array([["T1", "T2"], ["T3", "T4"]], dtype=object)
    lon_grid = np.array([[122.0, 123.0], [124.0, 125.0]])
    lat_grid = np.array([[10.0, 11.0], [12.0, 13.0]])

    alerts = service.check_for_alerts(
        risk_grid=risk_grid,
        state_grid=state_grid,
        tree_ids=tree_ids,
        orchard_id="orchard-a",
        risk_threshold=0.50,
        lon_grid=lon_grid,
        lat_grid=lat_grid,
    )

    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.affected_cells == [{"row": 0, "col": 1}]
    assert alert.affected_tree_ids == ["T2"]
    assert alert.centroid_lon == 123.0
    assert alert.centroid_lat == 11.0
    assert alert.recommended_actions
    assert "Inspect 1 flagged tree" in alert.recommended_actions[0]


def test_gate_condition_alerts_fire_when_biological_gate_opens():
    service = AlertService()

    alerts = service.check_gate_condition_alerts(
        diagnostics=[
            {"step": 0, "datetime": "2026-04-28T06:00:00Z", "gate_open": False},
            {"step": 1, "datetime": "2026-04-28T07:00:00Z", "gate_open": True},
            {"step": 2, "datetime": "2026-04-28T08:00:00Z", "gate_open": True},
            {"step": 3, "datetime": "2026-04-28T09:00:00Z", "gate_open": False},
        ],
        orchard_id="orchard-a",
        simulation_run_id="run-gate",
        pest_type="cecid",
        orchard_stage="fruitlet",
    )

    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.alert_id.startswith("alert_gate_")
    assert alert.severity == AlertSeverityEnum.HIGH
    assert alert.risk_value == pytest.approx(0.5)
    assert alert.affected_cells == []
    assert alert.affected_tree_ids == []
    assert alert.orchard_id == "orchard-a"
    assert alert.zone_name == "Cecid fly gate condition"
    assert "opened for 2 of 4 forecast hour" in alert.message
    assert "First favorable window: 2026-04-28T07:00:00Z" in alert.message
    assert alert.recommended_actions
    assert "fruitlet-stage" in alert.recommended_actions[0]


def test_gate_condition_alerts_skip_when_gate_stays_closed():
    service = AlertService()

    alerts = service.check_gate_condition_alerts(
        diagnostics=[
            {"step": 0, "gate_open": False},
            {"step": 1, "gate_open": False},
        ],
        orchard_id="orchard-a",
        pest_type="fruitfly",
        orchard_stage="mature",
    )

    assert alerts == []


def test_memory_alert_store_dedupes_active_duplicates():
    service = AlertService()

    base_alert = AlertCreate(
        alert_id="alert-memory-a",
        simulation_run_id="run-a",
        severity=AlertSeverityEnum.HIGH,
        risk_value=0.82,
        affected_cells=[],
        affected_tree_ids=[],
        orchard_id="orchard-a",
        zone_name="Cecid fly gate condition",
        message="Cecid fly biological gate opened.",
        centroid_lon=None,
        centroid_lat=None,
        recommended_actions=["Inspect fruitlet-stage blocks."],
    )
    duplicate_alert = AlertCreate(
        alert_id="alert-memory-b",
        simulation_run_id="run-b",
        severity=AlertSeverityEnum.HIGH,
        risk_value=0.90,
        affected_cells=[],
        affected_tree_ids=[],
        orchard_id="orchard-a",
        zone_name="Cecid fly gate condition",
        message="Cecid fly biological gate opened again.",
        centroid_lon=None,
        centroid_lat=None,
        recommended_actions=["Inspect fruitlet-stage blocks."],
    )

    service.store_alert_in_memory(base_alert)
    service.store_alert_in_memory(duplicate_alert)

    memory_alerts, total, active_count = service.get_memory_alerts()

    assert total == 1
    assert active_count == 1
    assert memory_alerts[0]["alert_id"] == "alert-memory-a"
    assert memory_alerts[0]["risk_value"] == 0.90


@pytest.mark.asyncio
async def test_simulation_background_alerts_store_memory_with_centroid(monkeypatch):
    alert_service.clear_memory_alerts()

    class BrokenSessionMaker:
        def __call__(self):
            return self

        async def __aenter__(self):
            raise RuntimeError("database unavailable")

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "api.core.database.async_session_maker",
        BrokenSessionMaker(),
    )

    result = SimpleNamespace(
        run_id="run-alert-test",
        risk_threshold=0.50,
        risk_geojson={
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[
                            [122.0, 10.0],
                            [123.0, 10.0],
                            [123.0, 11.0],
                            [122.0, 11.0],
                            [122.0, 10.0],
                        ]],
                    },
                    "properties": {
                        "row": 0,
                        "col": 0,
                        "risk": 0.60,
                        "state": "unbagged",
                        "tree_id": "T1",
                    },
                }
            ],
        },
    )

    await simulation_route.check_alerts(result=result, orchard_id="orchard-a")

    memory_alerts, total, active_count = alert_service.get_memory_alerts()
    assert total == 1
    assert active_count == 1
    assert memory_alerts[0]["simulation_run_id"] == "run-alert-test"
    assert memory_alerts[0]["affected_tree_ids"] == ["T1"]
    assert memory_alerts[0]["centroid_lon"] == pytest.approx(122.5)
    assert memory_alerts[0]["centroid_lat"] == pytest.approx(10.5)

    alert_service.clear_memory_alerts()


@pytest.mark.asyncio
async def test_simulation_background_alerts_store_gate_condition_memory(monkeypatch):
    alert_service.clear_memory_alerts()

    class BrokenSessionMaker:
        def __call__(self):
            return self

        async def __aenter__(self):
            raise RuntimeError("database unavailable")

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "api.core.database.async_session_maker",
        BrokenSessionMaker(),
    )

    result = SimpleNamespace(
        run_id="run-gate-alert-test",
        risk_threshold=0.50,
        risk_geojson={"type": "FeatureCollection", "features": []},
    )

    await simulation_route.check_alerts(
        result=result,
        orchard_id="orchard-a",
        gate_diagnostics=[
            {"step": 0, "datetime": "2026-04-28T06:00:00Z", "gate_open": False},
            {"step": 1, "datetime": "2026-04-28T07:00:00Z", "gate_open": True},
        ],
        pest_type="cecid",
        orchard_stage="fruitlet",
    )

    memory_alerts, total, active_count = alert_service.get_memory_alerts()
    assert total == 1
    assert active_count == 1
    assert memory_alerts[0]["simulation_run_id"] == "run-gate-alert-test"
    assert memory_alerts[0]["affected_tree_ids"] == []
    assert memory_alerts[0]["zone_name"] == "Cecid fly gate condition"
    assert "biological gate opened" in memory_alerts[0]["message"]

    alert_service.clear_memory_alerts()


@pytest.mark.asyncio
async def test_alert_list_includes_memory_fallback_when_database_is_available(monkeypatch):
    alert_service.clear_memory_alerts()
    alert_service.store_alert_in_memory(
        AlertCreate(
            alert_id="alert-memory-1",
            simulation_run_id="run-1",
            severity=AlertSeverityEnum.MEDIUM,
            risk_value=0.65,
            affected_cells=[],
            affected_tree_ids=["T1"],
            orchard_id="orchard-a",
            zone_name="Tree zone",
            message="Memory fallback alert",
            centroid_lon=122.5,
            centroid_lat=10.5,
            recommended_actions=["Inspect tree T1"],
        )
    )

    async def fake_get_alerts(db, status=None, orchard_id=None, limit=100, offset=0):
        return [], 0, 0

    monkeypatch.setattr(alert_service, "get_alerts", fake_get_alerts)

    response = await alerts_route.get_alerts(
        status=None,
        orchard_id=None,
        limit=100,
        offset=0,
        db=object(),
    )

    assert response.total == 1
    assert response.active_count == 1
    assert len(response.alerts) == 1
    assert response.alerts[0].alert_id == "alert-memory-1"
    assert response.alerts[0].centroid_lon == 122.5
    assert response.alerts[0].affected_tree_ids == ["T1"]
    assert response.alerts[0].recommended_actions == ["Inspect tree T1"]

    alert_service.clear_memory_alerts()


@pytest.mark.asyncio
async def test_alert_action_update_uses_memory_fallback(monkeypatch):
    alert_service.clear_memory_alerts()
    alert_service.store_alert_in_memory(
        AlertCreate(
            alert_id="alert-memory-action",
            simulation_run_id="run-1",
            severity=AlertSeverityEnum.MEDIUM,
            risk_value=0.65,
            affected_cells=[],
            affected_tree_ids=["T1"],
            orchard_id="orchard-a",
            zone_name="Tree zone",
            message="Memory fallback alert",
            centroid_lon=122.5,
            centroid_lat=10.5,
            recommended_actions=["Inspect tree T1"],
        )
    )

    async def fake_update_alert_action(*args, **kwargs):
        return None

    monkeypatch.setattr(alert_service, "update_alert_action", fake_update_alert_action)

    response = await alerts_route.update_alert_action(
        alert_id="alert-memory-action",
        action=AlertActionUpdate(
            action_status=AlertActionStatusEnum.IN_PROGRESS,
            assigned_to="field-team",
            notes="Field inspection started",
        ),
        db=object(),
    )

    assert response.action_status == AlertActionStatusEnum.IN_PROGRESS
    assert response.action_assigned_to == "field-team"
    assert response.action_notes == "Field inspection started"

    alert_service.clear_memory_alerts()
