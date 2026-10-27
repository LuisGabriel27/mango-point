"""History must not materialize maps, playback or complete responses for a list."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import JSON
from sqlalchemy.dialects import postgresql

from api.core.database import get_db
from api.core.security import get_current_active_user
from api.routes import simulation
from api.services.simulation_history_service import simulation_history_summary_query
from db.models import PestType


def test_history_projection_contains_only_summary_fields():
    query = simulation_history_summary_query()
    expected = {
        "run_id", "pest_type", "orchard_id", "simulation_mode", "hours", "started_at",
        "status", "peak_risk", "cells_at_risk", "n_infested_final", "weather_source",
        "has_time_series",
    }
    assert set(query.selected_columns.keys()) == expected
    # Direct column selection would transfer and decode the large result JSON.
    for field in query.selected_columns:
        assert not isinstance(field.type, JSON)


def test_summary_compatibility_fields_are_computed_in_postgresql():
    columns = simulation_history_summary_query().selected_columns
    mode = str(columns.simulation_mode.compile(dialect=postgresql.dialect(),
                                              compile_kwargs={"literal_binds": True}))
    playback = str(columns.has_time_series.compile(dialect=postgresql.dialect(),
                                                  compile_kwargs={"literal_binds": True}))
    assert "coalesce" in mode and "nullif" in mode
    assert "result_metadata ->> 'simulation_mode'" in mode
    assert "request_payload ->> 'simulation_mode'" in mode
    assert "'grid'" in mode
    # Legacy payload-only playback is inspected only when the dedicated field
    # is empty; no full JSON value is returned in either case.
    assert "CASE WHEN" in playback and "THEN true ELSE" in playback
    assert "response_payload -> 'time_series'" in playback
    assert "AS JSONB" in playback
    assert "json_array_length" in playback


@pytest.mark.parametrize("pest", list(PestType))
@pytest.mark.parametrize("mode", ["grid", "tree_graph"])
def test_history_api_preserves_summary_contract_and_requires_authentication(pest, mode):
    row = SimpleNamespace(
        run_id="summary-test", pest_type=pest, orchard_id="orchard-test",
        simulation_mode=mode, hours=48, started_at=datetime(2026, 10, 27, 0, 0),
        status="completed", peak_risk=0.75, cells_at_risk=4, n_infested_final=2,
        weather_source="open-meteo", has_time_series=True,
    )
    db = AsyncMock()
    visible, deleted = MagicMock(), MagicMock()
    visible.all.return_value = [row]
    deleted.scalars.return_value.all.return_value = ["deleted-test"]
    db.execute.side_effect = [visible, deleted]

    app = FastAPI()
    app.include_router(simulation.router, dependencies=[Depends(get_current_active_user)])

    async def database():
        yield db

    app.dependency_overrides[get_db] = database
    with TestClient(app) as client:
        assert client.get("/simulation/runs").status_code == 401
        db.execute.assert_not_awaited()
        app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(user_id=7)
        response = client.get("/simulation/runs", params={"orchard_id": "orchard-test", "limit": 10, "offset": 20})

    assert response.status_code == 200
    assert response.json() == {
        "runs": [{
            "run_id": "summary-test", "pest_type": pest.value, "orchard_id": "orchard-test",
            "simulation_mode": mode, "hours": 48, "started_at": "2026-10-27T00:00:00Z",
            "status": "completed", "peak_risk": 0.75, "cells_at_risk": 4,
            "n_infested_final": 2, "weather_source": "open-meteo", "has_time_series": True,
        }],
        "total": 1, "deleted_run_ids": ["deleted-test"],
    }
    visible.scalars.assert_not_called()
    query = db.execute.call_args_list[0].args[0].compile(dialect=postgresql.dialect())
    assert "ORDER BY simulation_run.started_at DESC" in str(query)
    assert 10 in query.params.values() and 20 in query.params.values()
    assert "orchard-test" in query.params.values()
