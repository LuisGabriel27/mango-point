from api.routes.simulation import _replayable_request_payload


def test_history_replaces_missing_seed_with_engine_seed():
    payload = _replayable_request_payload(
        {"pest_type": "cecid", "random_seed": None},
        random_seed=309463120,
    )

    assert payload["random_seed"] == 309463120


def test_history_preserves_an_explicit_request_seed():
    payload = _replayable_request_payload(
        {"pest_type": "cecid", "random_seed": 42},
        random_seed=309463120,
    )

    assert payload["random_seed"] == 42


def test_history_snapshots_model_version_without_losing_dashboard_state():
    payload = _replayable_request_payload(
        {"pest_type": "cecid", "dashboard_state": {"sensitivity": "standard"}},
        random_seed=42,
        model_version="2026.09-cecid-wind-v4",
    )

    assert payload["dashboard_state"] == {
        "sensitivity": "standard",
        "simulation_model_version": "2026.09-cecid-wind-v4",
    }


def test_history_snapshots_effective_tree_graph_distance():
    payload = _replayable_request_payload(
        {
            "pest_type": "fruitfly",
            "simulation_mode": "tree_graph",
            "tg_max_neighbor_dist_m": None,
        },
        random_seed=42,
        tg_max_neighbor_dist_m=25.0,
    )

    assert payload["tg_max_neighbor_dist_m"] == 25.0


def test_history_preserves_explicit_tree_graph_distance():
    payload = _replayable_request_payload(
        {
            "pest_type": "fruitfly",
            "simulation_mode": "tree_graph",
            "tg_max_neighbor_dist_m": 18.0,
        },
        random_seed=42,
        tg_max_neighbor_dist_m=25.0,
    )

    assert payload["tg_max_neighbor_dist_m"] == 18.0
