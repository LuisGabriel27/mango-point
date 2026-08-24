from pathlib import Path

import pytest

from api.services.cloud_sync_service import CloudSyncService, _async_database_url
from api.core.migrations import split_sql_statements
from scripts.restore_from_supabase import RESTORE_ORDER


ROOT = Path(__file__).resolve().parents[1]


class RecordingConnection:
    def __init__(self):
        self.calls = []

    async def execute(self, statement, params=None):
        self.calls.append((str(statement), params or {}))


def test_database_url_is_converted_for_asyncpg():
    assert _async_database_url("postgresql://user:pass@host/db").startswith(
        "postgresql+asyncpg://"
    )
    assert _async_database_url("postgres://user:pass@host/db").startswith(
        "postgresql+asyncpg://"
    )
    assert _async_database_url("postgresql+asyncpg://host/db") == "postgresql+asyncpg://host/db"


def test_migration_splitter_preserves_dollar_quoted_functions():
    statements = split_sql_statements(
        "CREATE FUNCTION f() RETURNS void AS $$ BEGIN PERFORM 1; END; $$ LANGUAGE plpgsql;"
    )
    assert len(statements) == 1
    assert "PERFORM 1;" in statements[0]


@pytest.mark.asyncio
async def test_remote_upsert_is_idempotent_and_serializes_json():
    remote = RecordingConnection()
    service = CloudSyncService()

    await service._upsert_remote_row(
        remote,
        "orchard",
        {
            "orchard_id": 7,
            "orchard_uid": "orchard-east",
            "name": "East Block",
            "geojson": {"type": "FeatureCollection", "features": []},
            "cecid_weed_zones": [{
                "id": "weeds-a",
                "label": "Canal weeds",
                "density": "moderate",
                "coordinates": [[122.0, 10.0], [122.1, 10.0], [122.1, 10.1]],
            }],
            "tree_count": 0,
            "is_active": True,
            "monitoring_enabled": True,
            "orchard_stage": "mature",
            "days_since_flowering": 60,
        },
    )

    sql, params = remote.calls[0]
    assert 'INSERT INTO "orchard"' in sql
    assert 'ON CONFLICT ("orchard_id") DO UPDATE' in sql
    assert '"type": "FeatureCollection"' in params["v_geojson"]
    assert '"density": "moderate"' in params["v_cecid_weed_zones"]


def test_sync_migration_has_transactional_triggers_and_excludes_weather_cache():
    migration = (ROOT / "db" / "migrations" / "0001_sync_backup.sql").read_text(
        encoding="utf-8"
    )

    assert "CREATE TABLE IF NOT EXISTS sync_outbox" in migration
    assert "CREATE TABLE IF NOT EXISTS sync_state" in migration
    assert "CREATE TABLE IF NOT EXISTS orchard_asset" in migration
    for table_name in (
        "user_account",
        "orchard",
        "tree",
        "pest",
        "simulation_run",
        "infestation_record",
        "environmental_condition",
        "mango_stage",
        "alert",
    ):
        assert f"trg_{table_name}_sync" in migration
    assert "trg_weather_cache_sync" not in migration

    asset_migration = (
        ROOT / "db" / "migrations" / "0003_disable_cloud_asset_replication.sql"
    ).read_text(encoding="utf-8")
    assert "DROP TRIGGER IF EXISTS trg_orchard_asset_sync" in asset_migration


def test_recipient_management_state_base_migration_repairs_database_defaults():
    local_migration = (
        ROOT / "db" / "migrations" / "0006_alert_email_recipient_state.sql"
    ).read_text(encoding="utf-8")
    cloud_migration = (
        ROOT
        / "supabase"
        / "migrations"
        / "202608240000_alert_email_recipient_state.sql"
    ).read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS alert_email_recipient_state" in local_migration
    assert "ALTER COLUMN updated_at SET DEFAULT NOW()" in local_migration
    assert "sync_outbox" not in local_migration
    assert "DROP TRIGGER IF EXISTS trg_alert_email_recipient_state_sync" in cloud_migration


def test_recipient_records_use_protected_cloud_sync_and_queue_existing_rows():
    local_migration = (
        ROOT / "db" / "migrations" / "0007_enable_alert_recipient_cloud_sync.sql"
    ).read_text(encoding="utf-8")
    cloud_migration = (
        ROOT
        / "supabase"
        / "migrations"
        / "202608240001_enable_alert_recipient_cloud_sync.sql"
    ).read_text(encoding="utf-8")

    for table_name, key_name in (
        ("alert_email_recipient", "recipient_id"),
        ("alert_email_recipient_state", "state_id"),
    ):
        assert f"trg_{table_name}_sync" in local_migration
        assert f"enqueue_mangopoint_sync_event('{key_name}')" in local_migration
        assert f"SELECT '{table_name}'" in local_migration

    assert "ENABLE ROW LEVEL SECURITY" in cloud_migration
    assert "FROM anon" in cloud_migration
    assert "FROM authenticated" in cloud_migration


def test_restore_order_respects_foreign_keys():
    assert RESTORE_ORDER.index("user_account") < RESTORE_ORDER.index("alert_email_recipient")
    assert "alert_email_recipient_state" in RESTORE_ORDER
    assert RESTORE_ORDER.index("orchard") < RESTORE_ORDER.index("tree")
    assert RESTORE_ORDER.index("pest") < RESTORE_ORDER.index("infestation_record")
    assert RESTORE_ORDER.index("simulation_run") < RESTORE_ORDER.index("alert")
    assert RESTORE_ORDER[-1] == "alert"
