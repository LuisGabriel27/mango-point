"""Isolated soft-deletion checks; never modify real simulation/observation rows."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from api.core.database import get_db
from api.core.security import get_current_active_user
from api.routes import simulation
from api.services.simulation_history_service import set_run_deleted
from api.services.system_overview_service import overview_queries, overview_window
from db.models import PestType, SimulationRun
from utils.datetime_utils import utcnow_naive


def stored_run(status="completed"):
    return SimulationRun(run_id="saved-test", pest_type=PestType.FRUIT_FLY, orchard_id="orchard-test",
                         status=status, hours=48, result_metadata={"model_version": "retained-version"},
                         request_payload={"random_seed": 42}, response_payload={"run_id": "saved-test"},
                         output_geojson={"features": [{"id": "tree-test"}]},
                         time_series=[{"hour": 1}], weather_data=[{"temperature": 27}])


def database_with(run):
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = run
    db.execute.return_value = result
    return db


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["completed", "failed", None])
async def test_delete_is_recoverable_idempotent_and_preserves_saved_evidence(status):
    run = stored_run(status)
    evidence = deepcopy({key: getattr(run, key) for key in (
        "request_payload", "response_payload", "output_geojson", "time_series", "weather_data")})
    db = database_with(run)
    deleted = await set_run_deleted(db, run.run_id, 7, deleted=True)
    assert deleted["deleted"] and run.status == "deleted"
    audit = deepcopy(run.result_metadata["history_deletion"])
    assert audit["previous_status"] == status
    assert audit["deleted_by"] == 7 and audit["deleted_at"]
    assert run.result_metadata["model_version"] == "retained-version"
    await set_run_deleted(db, run.run_id, 9, deleted=True)
    assert run.result_metadata["history_deletion"] == audit
    restored = await set_run_deleted(db, run.run_id, 7, deleted=False)
    assert not restored["deleted"] and run.status == status
    assert run.result_metadata["history_deletion"]["restored_by"] == 7
    assert {key: getattr(run, key) for key in evidence} == evidence
    db.delete.assert_not_called()
    for call in db.execute.call_args_list:
        sql = str(call.args[0].compile(dialect=postgresql.dialect()))
        assert "FOR UPDATE" in sql and "simulation_run.run_id =" in sql


@pytest.mark.asyncio
@pytest.mark.parametrize("run,status_code", [(None, 404), (stored_run("running"), 409)])
async def test_missing_and_running_runs_are_not_changed(run, status_code):
    from fastapi import HTTPException
    db = database_with(run)
    with pytest.raises(HTTPException) as error:
        await set_run_deleted(db, "saved-test", 7, deleted=True)
    assert error.value.status_code == status_code
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_deleted_details_and_single_run_exports_cannot_be_loaded():
    from fastapi import HTTPException
    for handler in (simulation.get_simulation_run, simulation.export_simulation_run):
        with pytest.raises(HTTPException) as error:
            await handler("saved-test", db=database_with(stored_run("deleted")))
        assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_history_filters_before_pagination_and_reports_cache_tombstones():
    db = AsyncMock()
    visible, deleted = MagicMock(), MagicMock()
    visible.scalars.return_value.all.return_value = []
    deleted.scalars.return_value.all.return_value = ["deleted-test"]
    db.execute.side_effect = [visible, deleted]
    result = await simulation.list_simulation_runs(orchard_id="orchard-test", limit=10, offset=10, db=db)
    assert result["runs"] == [] and result["deleted_run_ids"] == ["deleted-test"]
    queries = [call.args[0].compile(dialect=postgresql.dialect()) for call in db.execute.call_args_list]
    assert "status IS DISTINCT FROM" in str(queries[0])
    assert queries[0].params["status_1"] == "deleted"
    for query in queries:
        assert "simulation_run.orchard_id =" in str(query)


@pytest.mark.asyncio
async def test_bulk_export_and_overview_exclude_deleted_runs():
    db = AsyncMock()
    db.execute.return_value.scalars = MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = []
    await simulation.export_simulation_runs(orchard_id=None, period="all", year=None, month=None, limit=10, db=db)
    query = db.execute.call_args.args[0].compile(dialect=postgresql.dialect())
    assert "status IS DISTINCT FROM" in str(query) and query.params["status_1"] == "deleted"
    start, end = overview_window("month", utcnow_naive())
    overview = overview_queries("month", start, end)["runs"].compile(dialect=postgresql.dialect())
    assert "status IS DISTINCT FROM" in str(overview) and "deleted" in overview.params.values()


def test_delete_and_restore_require_authentication_and_route_to_the_selected_run():
    app = FastAPI()
    app.include_router(simulation.router, dependencies=[Depends(get_current_active_user)])
    db = database_with(stored_run())
    async def database(): yield db
    app.dependency_overrides[get_db] = database
    client = TestClient(app)
    assert client.delete("/simulation/runs/saved-test").status_code == 401
    assert client.post("/simulation/runs/saved-test/restore").status_code == 401
    db.commit.assert_not_awaited()
    app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(user_id=7)
    assert client.delete("/simulation/runs/saved-test").json()["deleted"] is True
    assert client.post("/simulation/runs/saved-test/restore").json()["deleted"] is False
