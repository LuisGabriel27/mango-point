from types import SimpleNamespace

from api.services.evaluation_service import EvaluationService


def _obs(tree_id):
    return SimpleNamespace(tree_id=tree_id)


def _feature(tree_id, risk, **extra):
    props = {"tree_id": tree_id, "risk": risk}
    props.update(extra)
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [122.0, 10.0]},
        "properties": props,
    }


def test_grid_output_matches_observations_by_tree_id():
    service = EvaluationService()
    risk_data = {
        "type": "FeatureCollection",
        "features": [
            _feature("1", 0.8, row=0, col=0),
            _feature("2", 0.7, row=0, col=1),
            _feature("3", 0.1, row=0, col=2),
        ],
    }

    metrics = service._compute_spatial_metrics(
        observations=[_obs(1), _obs(3)],
        trees=[],
        risk_data=risk_data,
        risk_threshold=0.5,
    )

    cm = metrics["confusion_matrix"]
    assert cm.true_positives == 1
    assert cm.false_positives == 1
    assert cm.false_negatives == 1
    assert cm.true_negatives == 0
    assert metrics["precision"] == 0.5
    assert metrics["recall"] == 0.5
    assert metrics["spatial_overlap_percentage"] == 33.33


def test_tree_graph_point_output_matches_observations_by_tree_id():
    service = EvaluationService()
    risk_data = {
        "type": "FeatureCollection",
        "features": [
            _feature("10", 0.9),
            _feature("11", 0.2),
            _feature("12", 0.8),
        ],
    }

    metrics = service._compute_spatial_metrics(
        observations=[_obs(10), _obs(11)],
        trees=[],
        risk_data=risk_data,
        risk_threshold=0.5,
    )

    cm = metrics["confusion_matrix"]
    assert cm.true_positives == 1
    assert cm.false_positives == 1
    assert cm.false_negatives == 1
    assert cm.true_negatives == 0


def test_unmatched_observation_counts_as_false_negative():
    service = EvaluationService()
    risk_data = {
        "type": "FeatureCollection",
        "features": [_feature("1", 0.9)],
    }

    metrics = service._compute_spatial_metrics(
        observations=[_obs(99)],
        trees=[],
        risk_data=risk_data,
        risk_threshold=0.5,
    )

    cm = metrics["confusion_matrix"]
    assert cm.true_positives == 0
    assert cm.false_positives == 1
    assert cm.false_negatives == 1
    assert cm.true_negatives == 0


def test_row_col_fallback_still_evaluates_cell_maps_without_tree_ids():
    service = EvaluationService()
    risk_data = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": []},
                "properties": {"row": 1, "col": 2, "risk": 0.9},
            }
        ],
    }

    metrics = service._compute_spatial_metrics(
        observations=[],
        trees=[],
        risk_data=risk_data,
        risk_threshold=0.5,
    )

    assert metrics["total_predictions"] == 1
