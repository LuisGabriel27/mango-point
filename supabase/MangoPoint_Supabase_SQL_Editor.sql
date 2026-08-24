-- MangoPoint: Supabase SQL Editor setup
--
-- Paste this entire file into the Supabase SQL Editor and click Run.
-- This creates the MangoPoint application schema and local-to-cloud backup
-- metadata. It does not upload existing local rows or orchard files.
-- It also does not create a Supabase Auth user: MangoPoint keeps using its
-- existing FastAPI JWT authentication and the private user_account table.
--
-- Do not paste .env values or service-role keys into this file.

BEGIN;

-- Supabase normally installs extensions in the extensions schema. Including
-- it in search_path lets this script work with both Supabase and local Docker.
SET search_path = public, extensions, gis;

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- -------------------------------------------------------------------------
-- Enum types
-- -------------------------------------------------------------------------

DO $$ BEGIN
    CREATE TYPE tree_status_enum AS ENUM ('healthy', 'infected', 'bagged', 'dead');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE tree_stage_enum AS ENUM ('dormant', 'flowering', 'fruitlet', 'mature');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE pest_attack_stage_enum AS ENUM ('fruitlet', 'mature');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE mango_stage_status_enum AS ENUM ('dormant', 'flowering', 'fruitlet', 'mature');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE pesttype AS ENUM ('cecid', 'fruitfly');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE alertseverity AS ENUM ('low', 'medium', 'high', 'critical');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE alertstatus AS ENUM ('active', 'acknowledged', 'resolved');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE user_role_enum AS ENUM ('admin', 'analyst', 'operator');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE OR REPLACE FUNCTION set_updated_at_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- -------------------------------------------------------------------------
-- MangoPoint application tables
-- -------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS user_account (
    user_id        SERIAL PRIMARY KEY,
    full_name      VARCHAR(200) NOT NULL,
    username       VARCHAR(100) NOT NULL,
    email          VARCHAR(255) NOT NULL,
    password_hash  VARCHAR(255) NOT NULL,
    role           user_role_enum NOT NULL DEFAULT 'admin',
    is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at  TIMESTAMP,
    created_at     TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_account_username ON user_account (username);
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_account_email ON user_account (email);
DROP TRIGGER IF EXISTS trg_user_account_set_updated_at ON user_account;
CREATE TRIGGER trg_user_account_set_updated_at
BEFORE UPDATE ON user_account
FOR EACH ROW EXECUTE FUNCTION set_updated_at_timestamp();

CREATE TABLE IF NOT EXISTS orchard (
    orchard_id SERIAL PRIMARY KEY,
    orchard_uid VARCHAR(100) NOT NULL,
    name VARCHAR(200) NOT NULL,
    owner_name VARCHAR(200),
    location VARCHAR(500),
    area_size NUMERIC(10, 2),
    tree_count INTEGER DEFAULT 0,
    geojson JSONB,
    cecid_weed_zones JSONB NOT NULL DEFAULT '[]'::jsonb,
    centroid_lon DOUBLE PRECISION,
    centroid_lat DOUBLE PRECISION,
    orthophoto_path VARCHAR(500),
    orthophoto_png_path VARCHAR(500),
    orthophoto_bounds JSONB,
    orthophoto_coordinates JSONB,
    dtm_path VARCHAR(500),
    dsm_path VARCHAR(500),
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    monitoring_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    orchard_stage VARCHAR(50) NOT NULL DEFAULT 'mature',
    days_since_flowering INTEGER NOT NULL DEFAULT 60,
    monitored_pest_types JSONB,
    last_monitoring_scan_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

ALTER TABLE IF EXISTS orchard
ADD COLUMN IF NOT EXISTS cecid_weed_zones JSONB NOT NULL DEFAULT '[]'::jsonb;

CREATE UNIQUE INDEX IF NOT EXISTS idx_orchard_uid ON orchard (orchard_uid);
CREATE INDEX IF NOT EXISTS idx_orchard_active ON orchard (is_active);
CREATE INDEX IF NOT EXISTS idx_orchard_monitoring_enabled ON orchard (monitoring_enabled);
DROP TRIGGER IF EXISTS trg_orchard_set_updated_at ON orchard;
CREATE TRIGGER trg_orchard_set_updated_at
BEFORE UPDATE ON orchard
FOR EACH ROW EXECUTE FUNCTION set_updated_at_timestamp();

CREATE TABLE IF NOT EXISTS tree (
    tree_id SERIAL PRIMARY KEY,
    orchard_id INTEGER NOT NULL REFERENCES orchard (orchard_id) ON DELETE CASCADE,
    x_coordinate DOUBLE PRECISION,
    y_coordinate DOUBLE PRECISION,
    geom GEOMETRY(POINT, 4326),
    age INTEGER,
    status tree_status_enum NOT NULL DEFAULT 'healthy',
    current_stage tree_stage_enum NOT NULL DEFAULT 'dormant'
);

CREATE INDEX IF NOT EXISTS idx_tree_orchard_id ON tree (orchard_id);
CREATE INDEX IF NOT EXISTS idx_tree_geom ON tree USING GIST (geom);

CREATE TABLE IF NOT EXISTS pest (
    pest_id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    scientific_name VARCHAR(300),
    attack_stage pest_attack_stage_enum NOT NULL
);

CREATE TABLE IF NOT EXISTS simulation_run (
    id SERIAL PRIMARY KEY,
    simulation_id SERIAL UNIQUE NOT NULL,
    run_id VARCHAR(100) UNIQUE NOT NULL,
    pest_type pesttype NOT NULL,
    orchard_id VARCHAR(100),
    orchard_geojson JSONB,
    bagged_tree_ids JSONB,
    treatment_applications JSONB,
    simulation_mode VARCHAR(50) DEFAULT 'grid',
    hours INTEGER DEFAULT 48,
    random_seed INTEGER,
    risk_threshold DOUBLE PRECISION DEFAULT 0.7,
    weather_source VARCHAR(50) DEFAULT 'synthetic',
    weather_data JSONB,
    output_geojson JSONB,
    request_payload JSONB,
    response_payload JSONB,
    result_metadata JSONB,
    time_series JSONB,
    timesteps JSONB,
    impact_assumptions JSONB,
    peak_risk DOUBLE PRECISION,
    cells_at_risk INTEGER,
    n_infested_final INTEGER,
    start_date TIMESTAMP,
    end_date TIMESTAMP,
    description TEXT,
    started_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    duration_seconds DOUBLE PRECISION,
    status VARCHAR(50) DEFAULT 'running',
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_simrun_run_id ON simulation_run (run_id);
CREATE INDEX IF NOT EXISTS idx_simrun_orchard_id ON simulation_run (orchard_id);

CREATE TABLE IF NOT EXISTS infestation_record (
    infestation_id SERIAL PRIMARY KEY,
    tree_id INTEGER NOT NULL REFERENCES tree (tree_id) ON DELETE CASCADE,
    pest_id INTEGER NOT NULL REFERENCES pest (pest_id) ON DELETE CASCADE,
    simulation_id INTEGER REFERENCES simulation_run (simulation_id) ON DELETE CASCADE,
    record_date TIMESTAMP,
    infected_status BOOLEAN DEFAULT FALSE,
    infestation_level NUMERIC(5, 2)
);

CREATE INDEX IF NOT EXISTS idx_infestation_tree_id ON infestation_record (tree_id);
CREATE INDEX IF NOT EXISTS idx_infestation_pest_id ON infestation_record (pest_id);
CREATE INDEX IF NOT EXISTS idx_infestation_simulation_id ON infestation_record (simulation_id);

CREATE TABLE IF NOT EXISTS environmental_condition (
    condition_id SERIAL PRIMARY KEY,
    simulation_id INTEGER NOT NULL REFERENCES simulation_run (simulation_id) ON DELETE CASCADE,
    condition_date TIMESTAMP,
    temperature NUMERIC(5, 2),
    humidity NUMERIC(5, 2),
    rainfall NUMERIC(7, 2),
    wind_speed NUMERIC(5, 2)
);

CREATE INDEX IF NOT EXISTS idx_envcond_simulation_id ON environmental_condition (simulation_id);

CREATE TABLE IF NOT EXISTS mango_stage (
    stage_id SERIAL PRIMARY KEY,
    simulation_id INTEGER NOT NULL REFERENCES simulation_run (simulation_id) ON DELETE CASCADE,
    stage_date TIMESTAMP,
    stage_status mango_stage_status_enum NOT NULL DEFAULT 'dormant'
);

CREATE INDEX IF NOT EXISTS idx_mangostage_simulation_id ON mango_stage (simulation_id);

CREATE TABLE IF NOT EXISTS alert (
    id SERIAL PRIMARY KEY,
    alert_id VARCHAR(100) UNIQUE NOT NULL,
    simulation_run_id VARCHAR(100) REFERENCES simulation_run (run_id),
    triggered_at TIMESTAMP DEFAULT NOW(),
    severity alertseverity DEFAULT 'high',
    status alertstatus DEFAULT 'active',
    risk_value DOUBLE PRECISION NOT NULL,
    affected_cells JSONB,
    affected_tree_ids JSONB,
    orchard_id VARCHAR(100),
    zone_name VARCHAR(100),
    centroid_lon DOUBLE PRECISION,
    centroid_lat DOUBLE PRECISION,
    message TEXT,
    recommended_actions JSONB,
    suggested_simulation_params JSONB,
    email_sent BOOLEAN DEFAULT FALSE,
    email_sent_at TIMESTAMP,
    sms_sent BOOLEAN DEFAULT FALSE,
    sms_sent_at TIMESTAMP,
    acknowledged_by VARCHAR(100),
    acknowledged_at TIMESTAMP,
    resolved_at TIMESTAMP,
    resolution_notes TEXT,
    action_status VARCHAR(50) NOT NULL DEFAULT 'pending',
    action_assigned_to VARCHAR(100),
    action_notes TEXT,
    action_due_at TIMESTAMP,
    action_completed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_alert_id ON alert (alert_id);
CREATE INDEX IF NOT EXISTS idx_alert_status ON alert (status);
CREATE INDEX IF NOT EXISTS idx_alert_severity ON alert (severity);

-- Admin-managed notification recipients. These contact records are backed up
-- through the server-side PostgreSQL connection and hidden from public APIs.
CREATE TABLE IF NOT EXISTS alert_email_recipient (
    recipient_id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    name VARCHAR(200),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by_user_id INTEGER REFERENCES user_account (user_id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_alert_email_recipient_email
    ON alert_email_recipient (email);
CREATE INDEX IF NOT EXISTS idx_alert_email_recipient_active
    ON alert_email_recipient (is_active);
DROP TRIGGER IF EXISTS trg_alert_email_recipient_set_updated_at ON alert_email_recipient;
CREATE TRIGGER trg_alert_email_recipient_set_updated_at
BEFORE UPDATE ON alert_email_recipient
FOR EACH ROW EXECUTE FUNCTION set_updated_at_timestamp();

CREATE TABLE IF NOT EXISTS alert_email_recipient_state (
    state_id INTEGER PRIMARY KEY DEFAULT 1,
    is_managed BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_alert_email_recipient_state_singleton CHECK (state_id = 1)
);

ALTER TABLE alert_email_recipient_state
    ALTER COLUMN state_id SET DEFAULT 1,
    ALTER COLUMN is_managed SET DEFAULT FALSE,
    ALTER COLUMN updated_at SET DEFAULT NOW();

INSERT INTO alert_email_recipient_state (state_id, is_managed, updated_at)
VALUES (1, EXISTS (SELECT 1 FROM alert_email_recipient), NOW())
ON CONFLICT (state_id) DO NOTHING;

DROP TRIGGER IF EXISTS trg_alert_email_recipient_state_sync
    ON alert_email_recipient_state;

ALTER TABLE alert_email_recipient ENABLE ROW LEVEL SECURITY;
ALTER TABLE alert_email_recipient_state ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL PRIVILEGES ON TABLE alert_email_recipient FROM anon;
        REVOKE ALL PRIVILEGES ON TABLE alert_email_recipient_state FROM anon;
        IF to_regclass('alert_email_recipient_recipient_id_seq') IS NOT NULL THEN
            REVOKE ALL PRIVILEGES ON SEQUENCE alert_email_recipient_recipient_id_seq FROM anon;
        END IF;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL PRIVILEGES ON TABLE alert_email_recipient FROM authenticated;
        REVOKE ALL PRIVILEGES ON TABLE alert_email_recipient_state FROM authenticated;
        IF to_regclass('alert_email_recipient_recipient_id_seq') IS NOT NULL THEN
            REVOKE ALL PRIVILEGES ON SEQUENCE alert_email_recipient_recipient_id_seq FROM authenticated;
        END IF;
    END IF;
END $$;

-- Transient cache: intentionally excluded from cloud replication below.
CREATE TABLE IF NOT EXISTS weather_cache (
    id SERIAL PRIMARY KEY,
    cache_key VARCHAR(200) UNIQUE NOT NULL,
    lon DOUBLE PRECISION NOT NULL,
    lat DOUBLE PRECISION NOT NULL,
    wind_speed_ms DOUBLE PRECISION NOT NULL,
    wind_direction_deg DOUBLE PRECISION NOT NULL,
    temperature_c DOUBLE PRECISION NOT NULL,
    humidity DOUBLE PRECISION,
    raw_response JSONB,
    fetched_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL,
    source VARCHAR(50) DEFAULT 'openweathermap'
);

CREATE INDEX IF NOT EXISTS idx_weather_cache_key ON weather_cache (cache_key);

-- -------------------------------------------------------------------------
-- Backup/synchronization metadata
-- -------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS sync_outbox (
    outbox_id BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL DEFAULT gen_random_uuid(),
    entity_type VARCHAR(100) NOT NULL,
    entity_key VARCHAR(200) NOT NULL,
    operation VARCHAR(20) NOT NULL CHECK (operation IN ('upsert', 'delete')),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_error TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    synced_at TIMESTAMP,
    CONSTRAINT uq_sync_outbox_event_id UNIQUE (event_id)
);

CREATE INDEX IF NOT EXISTS idx_sync_outbox_pending
    ON sync_outbox (synced_at, next_attempt_at, outbox_id);
CREATE INDEX IF NOT EXISTS idx_sync_outbox_entity
    ON sync_outbox (entity_type, entity_key, outbox_id);

CREATE TABLE IF NOT EXISTS sync_state (
    state_id INTEGER PRIMARY KEY DEFAULT 1,
    last_event_id BIGINT,
    last_success_at TIMESTAMP,
    last_attempt_at TIMESTAMP,
    pending_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_sync_state_singleton CHECK (state_id = 1)
);

INSERT INTO sync_state (state_id)
VALUES (1)
ON CONFLICT (state_id) DO NOTHING;

CREATE TABLE IF NOT EXISTS orchard_asset (
    asset_id BIGSERIAL PRIMARY KEY,
    orchard_id INTEGER NOT NULL REFERENCES orchard (orchard_id) ON DELETE CASCADE,
    asset_type VARCHAR(50) NOT NULL,
    local_path VARCHAR(500) NOT NULL,
    sha256 VARCHAR(64) NOT NULL,
    file_size BIGINT NOT NULL DEFAULT 0,
    mime_type VARCHAR(150),
    storage_bucket VARCHAR(150) NOT NULL DEFAULT 'orchard-assets',
    storage_key VARCHAR(500),
    sync_status VARCHAR(30) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_orchard_asset_type UNIQUE (orchard_id, asset_type)
);

CREATE INDEX IF NOT EXISTS idx_orchard_asset_orchard_id ON orchard_asset (orchard_id);

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

-- Orchard files and their manifest remain local-only.
DROP TRIGGER IF EXISTS trg_orchard_asset_sync ON orchard_asset;

DROP TRIGGER IF EXISTS trg_alert_email_recipient_sync ON alert_email_recipient;
CREATE TRIGGER trg_alert_email_recipient_sync
AFTER INSERT OR UPDATE OR DELETE ON alert_email_recipient
FOR EACH ROW EXECUTE FUNCTION enqueue_mangopoint_sync_event('recipient_id');

DROP TRIGGER IF EXISTS trg_alert_email_recipient_state_sync
    ON alert_email_recipient_state;
CREATE TRIGGER trg_alert_email_recipient_state_sync
AFTER INSERT OR UPDATE OR DELETE ON alert_email_recipient_state
FOR EACH ROW EXECUTE FUNCTION enqueue_mangopoint_sync_event('state_id');

-- Queue existing durable rows once. weather_cache and orchard_asset are omitted.
INSERT INTO sync_outbox (entity_type, entity_key, operation)
SELECT 'user_account', user_id::TEXT, 'upsert' FROM user_account source
WHERE NOT EXISTS (
    SELECT 1 FROM sync_outbox queued
    WHERE queued.entity_type = 'user_account'
      AND queued.entity_key = source.user_id::TEXT
      AND queued.operation = 'upsert'
      AND queued.synced_at IS NULL
);

INSERT INTO sync_outbox (entity_type, entity_key, operation)
SELECT 'alert_email_recipient', recipient_id::TEXT, 'upsert'
FROM alert_email_recipient source
WHERE NOT EXISTS (
    SELECT 1 FROM sync_outbox queued
    WHERE queued.entity_type = 'alert_email_recipient'
      AND queued.entity_key = source.recipient_id::TEXT
      AND queued.operation = 'upsert'
      AND queued.synced_at IS NULL
);

INSERT INTO sync_outbox (entity_type, entity_key, operation)
SELECT 'alert_email_recipient_state', state_id::TEXT, 'upsert'
FROM alert_email_recipient_state source
WHERE NOT EXISTS (
    SELECT 1 FROM sync_outbox queued
    WHERE queued.entity_type = 'alert_email_recipient_state'
      AND queued.entity_key = source.state_id::TEXT
      AND queued.operation = 'upsert'
      AND queued.synced_at IS NULL
);

INSERT INTO sync_outbox (entity_type, entity_key, operation)
SELECT 'orchard', orchard_id::TEXT, 'upsert' FROM orchard source
WHERE NOT EXISTS (
    SELECT 1 FROM sync_outbox queued
    WHERE queued.entity_type = 'orchard'
      AND queued.entity_key = source.orchard_id::TEXT
      AND queued.operation = 'upsert'
      AND queued.synced_at IS NULL
);

INSERT INTO sync_outbox (entity_type, entity_key, operation)
SELECT 'tree', tree_id::TEXT, 'upsert' FROM tree source
WHERE NOT EXISTS (
    SELECT 1 FROM sync_outbox queued
    WHERE queued.entity_type = 'tree'
      AND queued.entity_key = source.tree_id::TEXT
      AND queued.operation = 'upsert'
      AND queued.synced_at IS NULL
);

INSERT INTO sync_outbox (entity_type, entity_key, operation)
SELECT 'pest', pest_id::TEXT, 'upsert' FROM pest source
WHERE NOT EXISTS (
    SELECT 1 FROM sync_outbox queued
    WHERE queued.entity_type = 'pest'
      AND queued.entity_key = source.pest_id::TEXT
      AND queued.operation = 'upsert'
      AND queued.synced_at IS NULL
);

INSERT INTO sync_outbox (entity_type, entity_key, operation)
SELECT 'simulation_run', id::TEXT, 'upsert' FROM simulation_run source
WHERE NOT EXISTS (
    SELECT 1 FROM sync_outbox queued
    WHERE queued.entity_type = 'simulation_run'
      AND queued.entity_key = source.id::TEXT
      AND queued.operation = 'upsert'
      AND queued.synced_at IS NULL
);

INSERT INTO sync_outbox (entity_type, entity_key, operation)
SELECT 'infestation_record', infestation_id::TEXT, 'upsert' FROM infestation_record source
WHERE NOT EXISTS (
    SELECT 1 FROM sync_outbox queued
    WHERE queued.entity_type = 'infestation_record'
      AND queued.entity_key = source.infestation_id::TEXT
      AND queued.operation = 'upsert'
      AND queued.synced_at IS NULL
);

INSERT INTO sync_outbox (entity_type, entity_key, operation)
SELECT 'environmental_condition', condition_id::TEXT, 'upsert' FROM environmental_condition source
WHERE NOT EXISTS (
    SELECT 1 FROM sync_outbox queued
    WHERE queued.entity_type = 'environmental_condition'
      AND queued.entity_key = source.condition_id::TEXT
      AND queued.operation = 'upsert'
      AND queued.synced_at IS NULL
);

INSERT INTO sync_outbox (entity_type, entity_key, operation)
SELECT 'mango_stage', stage_id::TEXT, 'upsert' FROM mango_stage source
WHERE NOT EXISTS (
    SELECT 1 FROM sync_outbox queued
    WHERE queued.entity_type = 'mango_stage'
      AND queued.entity_key = source.stage_id::TEXT
      AND queued.operation = 'upsert'
      AND queued.synced_at IS NULL
);

INSERT INTO sync_outbox (entity_type, entity_key, operation)
SELECT 'alert', id::TEXT, 'upsert' FROM alert source
WHERE NOT EXISTS (
    SELECT 1 FROM sync_outbox queued
    WHERE queued.entity_type = 'alert'
      AND queued.entity_key = source.id::TEXT
      AND queued.operation = 'upsert'
      AND queued.synced_at IS NULL
);

RESET search_path;
COMMIT;
