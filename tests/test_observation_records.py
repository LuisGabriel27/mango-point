from datetime import datetime

from db.models import InfestationRecord


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
