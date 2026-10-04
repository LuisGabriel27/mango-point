from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts import sync_supabase_schema as schema_sync
from scripts.sync_supabase_schema import executable_statements, schema_digest


def test_schema_digest_changes_with_schema_content():
    assert schema_digest("SELECT 1;") == schema_digest("SELECT 1;")
    assert schema_digest("SELECT 1;") != schema_digest("SELECT 2;")


def test_executable_statements_omits_only_outer_transaction_markers():
    sql = """
    BEGIN;
    SET search_path = public;
    DO $$ BEGIN PERFORM 1; END $$;
    COMMIT;
    """

    statements = executable_statements(sql)

    assert len(statements) == 2
    assert statements[0] == "SET search_path = public"
    assert statements[1] == "DO $$ BEGIN PERFORM 1; END $$"


@pytest.fixture
def remote_schema(monkeypatch, tmp_path):
    from api.services import cloud_sync_service

    schema = tmp_path / "schema.sql"
    schema.write_text("BEGIN; SELECT 1; SELECT 2; COMMIT;", encoding="utf-8")
    monkeypatch.setattr(schema_sync, "SCHEMA_PATH", schema)

    remote = AsyncMock()
    engine = MagicMock()
    engine.begin.return_value.__aenter__.return_value = remote
    engine.connect.return_value.__aenter__.return_value = remote
    service = MagicMock(configured=True)
    service._get_remote_engine.return_value = engine
    service.close = AsyncMock()
    monkeypatch.setattr(cloud_sync_service, "CloudSyncService", lambda: service)
    return remote, engine, service, schema_digest(schema.read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_unchanged_schema_does_not_execute_schema_or_update_hash(remote_schema):
    remote, engine, service, digest = remote_schema
    remote.scalar.side_effect = [True, digest]

    assert await schema_sync.sync_schema(apply=True) is False

    remote.exec_driver_sql.assert_not_awaited()
    assert remote.execute.await_count == 1  # Transaction lock only.
    assert "pg_advisory_xact_lock" in str(remote.execute.call_args.args[0])
    engine.connect.assert_not_called()
    service.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_schema_and_hash_are_written_inside_one_transaction(remote_schema):
    remote, engine, service, digest = remote_schema
    remote.scalar.return_value = False

    assert await schema_sync.sync_schema(apply=True) is True

    assert [call.args[0] for call in remote.exec_driver_sql.await_args_list] == [
        "SELECT 1", "SELECT 2"
    ]
    hash_write = remote.execute.await_args_list[-1]
    assert "INSERT INTO public.mangopoint_schema_state" in str(hash_write.args[0])
    assert hash_write.args[1]["schema_hash"] == digest
    engine.begin.assert_called_once()
    engine.begin.return_value.__aexit__.assert_awaited_once_with(None, None, None)
    service.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_schema_does_not_record_hash_and_exits_with_error(remote_schema):
    remote, engine, service, _ = remote_schema
    remote.scalar.return_value = False
    failure = RuntimeError("invalid SQL")
    remote.exec_driver_sql.side_effect = [None, failure]

    with pytest.raises(RuntimeError, match="invalid SQL"):
        await schema_sync.sync_schema(apply=True)

    assert remote.execute.await_count == 1  # No success hash on failure.
    assert engine.begin.return_value.__aexit__.call_args.args[1] is failure
    service.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_mode_reads_without_writing(remote_schema):
    remote, engine, service, _ = remote_schema
    remote.scalar.return_value = False

    assert await schema_sync.sync_schema(apply=False) is True

    remote.execute.assert_not_awaited()
    remote.exec_driver_sql.assert_not_awaited()
    engine.begin.assert_not_called()
    service.close.assert_awaited_once()


def test_cli_does_not_print_connection_secrets(monkeypatch, capsys):
    monkeypatch.setattr(schema_sync.sys, "argv", ["sync_supabase_schema", "--apply"])
    monkeypatch.setattr(
        schema_sync, "_run_with_timeout",
        AsyncMock(side_effect=RuntimeError("postgresql://user:private-password@host/db")),
    )

    with pytest.raises(SystemExit) as error:
        schema_sync.main()

    assert error.value.code == 1
    output = capsys.readouterr().err
    assert "RuntimeError" in output
    assert "private-password" not in output


def test_pooler_failure_explains_missing_tenant_without_echoing_user():
    error = RuntimeError("(ENOTFOUND) tenant/user private-project-user not found")

    reason = schema_sync._safe_failure_reason(error)

    assert "could not find the configured project or pooler user" in reason
    assert "private-project-user" not in reason


def test_tracking_migration_matches_consolidated_schema():
    migration = schema_sync.PROJECT_ROOT / "supabase/migrations/202610040001_schema_sync_state.sql"
    consolidated = executable_statements(schema_sync.SCHEMA_PATH.read_text(encoding="utf-8"))

    for statement in executable_statements(migration.read_text(encoding="utf-8")):
        assert statement in consolidated
