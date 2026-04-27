import pytest

from utils.decision_support import (
    DecisionZone,
    build_action_plan,
    format_action_plan,
)


def _point_feature(tree_id, risk, state="unbagged", lon=122.0, lat=10.0):
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "tree_id": tree_id,
            "risk": risk,
            "state": state,
        },
    }


def _grid_feature(row, col, risk, state="unbagged"):
    lon = 122.0 + col * 0.0001
    lat = 10.0 + row * 0.0001
    return {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [lon, lat],
                [lon + 0.00005, lat],
                [lon + 0.00005, lat + 0.00005],
                [lon, lat + 0.00005],
                [lon, lat],
            ]],
        },
        "properties": {
            "row": row,
            "col": col,
            "risk": risk,
            "state": state,
        },
    }


def _geojson(features):
    return {"type": "FeatureCollection", "features": features}


def test_action_plan_prioritizes_critical_trees_by_risk():
    plan = build_action_plan(
        _geojson([
            _point_feature("T1", 0.80, lon=122.0, lat=10.0),
            _point_feature("T2", 0.45, lon=122.1, lat=10.1),
            _point_feature("T3", 0.95, lon=122.2, lat=10.2),
            _point_feature("T4", 0.99, state="dead", lon=122.3, lat=10.3),
        ]),
        pest_type="cecid",
        orchard_stage="fruitlet",
    )

    assert len(plan) == 2
    critical = plan[0]
    monitor = plan[1]

    assert critical.zone == DecisionZone.CRITICAL
    assert critical.priority == "Urgent"
    assert critical.action_type == "targeted_control"
    assert critical.target_count == 2
    assert critical.max_risk == pytest.approx(0.95)
    assert critical.tree_ids == ["T3", "T1"]
    assert "fruitlet" in critical.rationale.lower()
    assert any("fruitlet" in step.lower() for step in critical.recommended_steps)

    assert monitor.zone == DecisionZone.MONITOR
    assert monitor.priority == "Medium"
    assert monitor.tree_ids == ["T2"]


def test_action_plan_gives_high_priority_to_monitor_only_fruit_fly_risk():
    plan = build_action_plan(
        _geojson([
            _point_feature("M1", 0.35),
            _point_feature("M2", 0.55),
            _point_feature("S1", 0.10),
        ]),
        pest_type="fruitfly",
        orchard_stage="mature",
    )

    assert len(plan) == 1
    item = plan[0]
    assert item.zone == DecisionZone.MONITOR
    assert item.priority == "High"
    assert item.timing == "Within 24 hours"
    assert item.target_count == 2
    assert item.tree_ids == ["M2", "M1"]
    assert any("trap" in step.lower() for step in item.recommended_steps)


def test_action_plan_returns_routine_scouting_when_all_risk_is_low():
    plan = build_action_plan(
        _geojson([
            _point_feature("S1", 0.05),
            _point_feature("S2", 0.20),
        ]),
        pest_type="cecid",
        orchard_stage="flowering",
    )

    assert len(plan) == 1
    item = plan[0]
    assert item.zone == DecisionZone.NO_ACTION
    assert item.priority == "Routine"
    assert item.action_type == "routine_monitoring"
    assert item.target_count == 2


def test_action_plan_verifies_bagged_risky_trees_instead_of_control_task():
    plan = build_action_plan(
        _geojson([
            _point_feature("B1", 0.92, state="bagged"),
            _point_feature("S1", 0.10),
        ]),
        pest_type="cecid",
    )

    assert len(plan) == 1
    item = plan[0]
    assert item.action_type == "protection_check"
    assert item.title == "Verify protected flagged trees"
    assert item.tree_ids == ["B1"]
    assert any("bagging" in step.lower() for step in item.recommended_steps)


def test_action_plan_supports_grid_cells_without_tree_ids():
    plan = build_action_plan(
        _geojson([
            _grid_feature(2, 3, 0.90),
            _grid_feature(5, 7, 0.72),
            _grid_feature(8, 1, 0.20),
        ]),
        pest_type="cecid",
    )

    assert len(plan) == 1
    item = plan[0]
    assert item.zone == DecisionZone.CRITICAL
    assert item.cells == [{"row": 2, "col": 3}, {"row": 5, "col": 7}]
    assert "rows 2-5" in item.scope_label
    assert "cols 3-7" in item.scope_label


def test_format_action_plan_is_json_friendly():
    plan = build_action_plan(
        _geojson([_point_feature("T9", 0.88)]),
        pest_type="cecid",
    )

    formatted = format_action_plan(plan)

    assert formatted[0]["zone"] == int(DecisionZone.CRITICAL)
    assert formatted[0]["zone_label"] == "Critical: Targeted Action"
    assert formatted[0]["tree_ids"] == ["T9"]
