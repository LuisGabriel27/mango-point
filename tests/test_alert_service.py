from api.models.schemas import AlertSeverityEnum
from api.services.alert_service import AlertService


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
