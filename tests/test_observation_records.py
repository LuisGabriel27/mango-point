from datetime import datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from api.models.schemas import ObservationSubmission
from api.routes.observations import _new_record, _to_response
from db.models import InfestationRecord, Tree


def test_infestation_record_accepts_ground_truth_without_simulation():
    record = InfestationRecord(
        tree_id=1,
        pest_id=1,
        simulation_id=None,
        record_date=datetime(2026, 4, 27, 9, 0, 0),
        infected_status=True,
        infestation_level=70.0,
    )

    assert record.simulation_id is None


def test_infestation_record_simulation_id_is_nullable():
    column = InfestationRecord.__table__.c.simulation_id

    assert column.nullable is True


def test_observation_schema_accepts_portable_tree_id_and_forecast_link():
    observation = ObservationSubmission(
        tree_id="T-042",
        orchard_id="default-orchard",
        observed_pest="cecid",
        timestamp="2026-09-13T06:00:00+08:00",
        presence="present",
        severity=0.65,
        affected_count=13,
        inspected_count=20,
        method="fruit_sampling",
        observer_id="field-team-a",
        simulation_run_id="sim_demo",
        forecast_risk=0.72,
        forecast_lead_hours=24,
    )

    assert observation.tree_id == "T-042"
    assert observation.presence.value == "present"
    assert observation.timestamp.utcoffset().total_seconds() == 8 * 3600


def test_observation_schema_rejects_impossible_counts():
    with pytest.raises(ValidationError, match="affected_count cannot exceed inspected_count"):
        ObservationSubmission(
            tree_id="T-1",
            orchard_id="orchard-a",
            observed_pest="cecid",
            timestamp="2026-09-13T06:00:00+08:00",
            affected_count=11,
            inspected_count=10,
        )


def test_observation_record_copies_append_only_verification_fields():
    payload = ObservationSubmission(
        tree_id="T-7",
        orchard_id="orchard-a",
        observed_pest="fruitfly",
        timestamp="2026-09-13T17:30:00+08:00",
        presence="absent",
        affected_count=0,
        inspected_count=12,
        method="visual_inspection",
        observer_id="Maria",
        notes="No punctures seen",
        image_url="https://example.test/tree-7.jpg",
        simulation_run_id="sim_reference",
        forecast_risk=0.41,
        forecast_lead_hours=12,
    )
    record = _new_record(
        payload,
        tree=SimpleNamespace(tree_id=17, external_id="T-7"),
        pest=SimpleNamespace(pest_id=2),
    )

    assert record.simulation_id is None
    assert record.tree_external_id == "T-7"
    assert record.observation_status == "absent"
    assert record.infected_status is False
    assert record.inspected_count == 12
    assert record.verification_run_id == "sim_reference"


def test_observation_response_uses_external_tree_identity():
    record = InfestationRecord(
        infestation_id=4,
        tree_id=17,
        tree_external_id="T-7",
        pest_id=2,
        simulation_id=None,
        record_date=datetime(2026, 9, 13, 9, 30),
        infected_status=True,
        observation_status="present",
        infestation_level=55,
        affected_count=3,
        inspected_count=10,
        observation_method="fruit_sampling",
        created_at=datetime(2026, 9, 13, 9, 31),
    )
    response = _to_response(
        record,
        pest_type="cecid",
        orchard=SimpleNamespace(orchard_uid="orchard-a", orchard_id=1),
        tree=SimpleNamespace(tree_id=17, external_id="T-7"),
    )

    assert response.tree_id == "T-7"
    assert response.database_tree_id == 17
    assert response.orchard_id == "orchard-a"
    assert response.presence.value == "present"


def test_tree_enum_storage_matches_lowercase_postgres_labels():
    assert Tree.__table__.c.status.type.enums == [
        "healthy", "infected", "bagged", "dead", "history_infected", "suspect",
    ]
    assert Tree.__table__.c.current_stage.type.enums == [
        "dormant", "flowering", "fruitlet", "mature",
    ]
