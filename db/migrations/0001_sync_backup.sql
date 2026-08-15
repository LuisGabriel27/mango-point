-- MangoPoint sync and cloud-backup migration.
-- The domain schema is created by db/schema.sql/SQLAlchemy first.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS sync_outbox (
    outbox_id      BIGSERIAL PRIMARY KEY,
    event_id       UUID NOT NULL DEFAULT gen_random_uuid(),
    entity_type    VARCHAR(100) NOT NULL,
    entity_key     VARCHAR(200) NOT NULL,
    operation      VARCHAR(20) NOT NULL CHECK (operation IN ('upsert', 'delete')),
    attempt_count  INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_error     TEXT,
    created_at     TIMESTAMP NOT NULL DEFAULT NOW(),
    synced_at      TIMESTAMP,
    CONSTRAINT uq_sync_outbox_event_id UNIQUE (event_id)
);

CREATE INDEX IF NOT EXISTS idx_sync_outbox_pending
    ON sync_outbox (synced_at, next_attempt_at, outbox_id);

CREATE INDEX IF NOT EXISTS idx_sync_outbox_entity
    ON sync_outbox (entity_type, entity_key, outbox_id);

CREATE TABLE IF NOT EXISTS sync_state (
    state_id        INTEGER PRIMARY KEY DEFAULT 1,
    last_event_id   BIGINT,
    last_success_at TIMESTAMP,
    last_attempt_at TIMESTAMP,
    pending_count   INTEGER NOT NULL DEFAULT 0,
    last_error      TEXT,
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_sync_state_singleton CHECK (state_id = 1)
);

INSERT INTO sync_state (state_id)
VALUES (1)
ON CONFLICT (state_id) DO NOTHING;

CREATE TABLE IF NOT EXISTS orchard_asset (
    asset_id       BIGSERIAL PRIMARY KEY,
    orchard_id     INTEGER NOT NULL REFERENCES orchard (orchard_id) ON DELETE CASCADE,
    asset_type     VARCHAR(50) NOT NULL,
    local_path     VARCHAR(500) NOT NULL,
    sha256         VARCHAR(64) NOT NULL,
    file_size      BIGINT NOT NULL DEFAULT 0,
    mime_type      VARCHAR(150),
    storage_bucket VARCHAR(150) NOT NULL DEFAULT 'orchard-assets',
    storage_key    VARCHAR(500),
    sync_status    VARCHAR(30) NOT NULL DEFAULT 'pending',
    created_at     TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_orchard_asset_type UNIQUE (orchard_id, asset_type)
);

CREATE INDEX IF NOT EXISTS idx_orchard_asset_orchard_id
    ON orchard_asset (orchard_id);

CREATE OR REPLACE FUNCTION enqueue_mangopoint_sync_event()
RETURNS TRIGGER AS $$
DECLARE
    key_value TEXT;
    event_operation VARCHAR(20);
BEGIN
    IF current_setting('mangopoint.sync_disabled', true) = 'true' THEN
        RETURN COALESCE(NEW, OLD);
    END IF;

    IF TG_OP = 'DELETE' THEN
        key_value := to_jsonb(OLD) ->> TG_ARGV[0];
        event_operation := 'delete';
    ELSE
        key_value := to_jsonb(NEW) ->> TG_ARGV[0];
        event_operation := 'upsert';
    END IF;

    INSERT INTO sync_outbox (entity_type, entity_key, operation)
    VALUES (TG_TABLE_NAME, key_value, event_operation);

    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_user_account_sync ON user_account;
CREATE TRIGGER trg_user_account_sync
AFTER INSERT OR UPDATE OR DELETE ON user_account
FOR EACH ROW EXECUTE FUNCTION enqueue_mangopoint_sync_event('user_id');

DROP TRIGGER IF EXISTS trg_orchard_sync ON orchard;
CREATE TRIGGER trg_orchard_sync
AFTER INSERT OR UPDATE OR DELETE ON orchard
FOR EACH ROW EXECUTE FUNCTION enqueue_mangopoint_sync_event('orchard_id');

DROP TRIGGER IF EXISTS trg_tree_sync ON tree;
CREATE TRIGGER trg_tree_sync
AFTER INSERT OR UPDATE OR DELETE ON tree
FOR EACH ROW EXECUTE FUNCTION enqueue_mangopoint_sync_event('tree_id');

DROP TRIGGER IF EXISTS trg_pest_sync ON pest;
CREATE TRIGGER trg_pest_sync
AFTER INSERT OR UPDATE OR DELETE ON pest
FOR EACH ROW EXECUTE FUNCTION enqueue_mangopoint_sync_event('pest_id');

DROP TRIGGER IF EXISTS trg_simulation_run_sync ON simulation_run;
CREATE TRIGGER trg_simulation_run_sync
AFTER INSERT OR UPDATE OR DELETE ON simulation_run
FOR EACH ROW EXECUTE FUNCTION enqueue_mangopoint_sync_event('id');

DROP TRIGGER IF EXISTS trg_infestation_record_sync ON infestation_record;
CREATE TRIGGER trg_infestation_record_sync
AFTER INSERT OR UPDATE OR DELETE ON infestation_record
FOR EACH ROW EXECUTE FUNCTION enqueue_mangopoint_sync_event('infestation_id');

DROP TRIGGER IF EXISTS trg_environmental_condition_sync ON environmental_condition;
CREATE TRIGGER trg_environmental_condition_sync
AFTER INSERT OR UPDATE OR DELETE ON environmental_condition
FOR EACH ROW EXECUTE FUNCTION enqueue_mangopoint_sync_event('condition_id');

DROP TRIGGER IF EXISTS trg_mango_stage_sync ON mango_stage;
CREATE TRIGGER trg_mango_stage_sync
AFTER INSERT OR UPDATE OR DELETE ON mango_stage
FOR EACH ROW EXECUTE FUNCTION enqueue_mangopoint_sync_event('stage_id');

DROP TRIGGER IF EXISTS trg_alert_sync ON alert;
CREATE TRIGGER trg_alert_sync
AFTER INSERT OR UPDATE OR DELETE ON alert
FOR EACH ROW EXECUTE FUNCTION enqueue_mangopoint_sync_event('id');

DROP TRIGGER IF EXISTS trg_orchard_asset_sync ON orchard_asset;
CREATE TRIGGER trg_orchard_asset_sync
AFTER INSERT OR UPDATE OR DELETE ON orchard_asset
FOR EACH ROW EXECUTE FUNCTION enqueue_mangopoint_sync_event('asset_id');

-- Backfill pre-existing rows so the first sync also migrates current local data.
INSERT INTO sync_outbox (entity_type, entity_key, operation)
SELECT 'user_account', user_id::TEXT, 'upsert' FROM user_account;
INSERT INTO sync_outbox (entity_type, entity_key, operation)
SELECT 'orchard', orchard_id::TEXT, 'upsert' FROM orchard;
INSERT INTO sync_outbox (entity_type, entity_key, operation)
SELECT 'tree', tree_id::TEXT, 'upsert' FROM tree;
INSERT INTO sync_outbox (entity_type, entity_key, operation)
SELECT 'pest', pest_id::TEXT, 'upsert' FROM pest;
INSERT INTO sync_outbox (entity_type, entity_key, operation)
SELECT 'simulation_run', id::TEXT, 'upsert' FROM simulation_run;
INSERT INTO sync_outbox (entity_type, entity_key, operation)
SELECT 'infestation_record', infestation_id::TEXT, 'upsert' FROM infestation_record;
INSERT INTO sync_outbox (entity_type, entity_key, operation)
SELECT 'environmental_condition', condition_id::TEXT, 'upsert' FROM environmental_condition;
INSERT INTO sync_outbox (entity_type, entity_key, operation)
SELECT 'mango_stage', stage_id::TEXT, 'upsert' FROM mango_stage;
INSERT INTO sync_outbox (entity_type, entity_key, operation)
SELECT 'alert', id::TEXT, 'upsert' FROM alert;
