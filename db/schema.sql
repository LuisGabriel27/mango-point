-- ============================================================
-- MangoPoint — PostgreSQL + PostGIS Schema (Consolidated)
-- ============================================================
-- Single schema for the spatiotemporal pest spread simulation.
--
-- Usage:
--   psql -d mangopoint -f db/schema.sql
--
-- Prerequisites:
--   CREATE DATABASE mangopoint;
--   \c mangopoint
-- ============================================================

-- ────────────────────────────────────────────
--  Pre-flight: ensure PostGIS is available
-- ────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_available_extensions WHERE name = 'postgis'
    ) THEN
        RAISE EXCEPTION
            'PostGIS extension is NOT available in this PostgreSQL installation. '
            'Please install PostGIS for PostgreSQL 16 first. '
            'On Windows: download the PostGIS bundle from https://postgis.net/install/ '
            'or use Stack Builder from the PostgreSQL installation folder.';
    END IF;
END $$;

-- Enable PostGIS extension
CREATE EXTENSION IF NOT EXISTS postgis;


-- ────────────────────────────────────────────
--  ENUM Definitions
-- ────────────────────────────────────────────

DO $$ BEGIN
    CREATE TYPE tree_status_enum AS ENUM (
        'healthy', 'infected', 'bagged', 'dead'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE tree_stage_enum AS ENUM (
        'dormant', 'flowering', 'fruitlet', 'mature'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE pest_attack_stage_enum AS ENUM (
        'fruitlet', 'mature'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE mango_stage_status_enum AS ENUM (
        'dormant', 'flowering', 'fruitlet', 'mature'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE pesttype AS ENUM (
        'cecid', 'fruitfly'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE alertseverity AS ENUM (
        'low', 'medium', 'high', 'critical'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE alertstatus AS ENUM (
        'active', 'acknowledged', 'resolved'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE user_role_enum AS ENUM (
        'admin', 'analyst', 'operator'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE OR REPLACE FUNCTION set_updated_at_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ────────────────────────────────────────────
--  1. orchard
-- ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_account (
    user_id        SERIAL          PRIMARY KEY,
    full_name      VARCHAR(200)    NOT NULL,
    username       VARCHAR(100)    NOT NULL,
    email          VARCHAR(255)    NOT NULL,
    password_hash  VARCHAR(255)    NOT NULL,
    role           user_role_enum  NOT NULL DEFAULT 'admin',
    is_active      BOOLEAN         NOT NULL DEFAULT TRUE,
    last_login_at  TIMESTAMP,
    created_at     TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_account_username ON user_account (username);
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_account_email    ON user_account (email);

DROP TRIGGER IF EXISTS trg_user_account_set_updated_at ON user_account;
CREATE TRIGGER trg_user_account_set_updated_at
BEFORE UPDATE ON user_account
FOR EACH ROW
EXECUTE FUNCTION set_updated_at_timestamp();


CREATE TABLE IF NOT EXISTS orchard (
    orchard_id   SERIAL       PRIMARY KEY,
    orchard_uid  VARCHAR(100) NOT NULL,
    name         VARCHAR(200) NOT NULL,
    owner_name   VARCHAR(200),
    location     VARCHAR(500),
    area_size    NUMERIC(10, 2),
    tree_count   INTEGER      DEFAULT 0,
    geojson      JSONB,
    centroid_lon DOUBLE PRECISION,
    centroid_lat DOUBLE PRECISION,
    orthophoto_path VARCHAR(500),
    orthophoto_png_path VARCHAR(500),
    orthophoto_bounds JSONB,
    orthophoto_coordinates JSONB,
    dtm_path VARCHAR(500),
    dsm_path VARCHAR(500),
    description  TEXT,
    is_active    BOOLEAN      NOT NULL DEFAULT TRUE,
    monitoring_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    orchard_stage VARCHAR(50) NOT NULL DEFAULT 'mature',
    days_since_flowering INTEGER NOT NULL DEFAULT 60,
    monitored_pest_types JSONB,
    last_monitoring_scan_at TIMESTAMP,
    created_at   TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_orchard_uid ON orchard (orchard_uid);
CREATE INDEX IF NOT EXISTS idx_orchard_active     ON orchard (is_active);
CREATE INDEX IF NOT EXISTS idx_orchard_monitoring_enabled ON orchard (monitoring_enabled);

DROP TRIGGER IF EXISTS trg_orchard_set_updated_at ON orchard;
CREATE TRIGGER trg_orchard_set_updated_at
BEFORE UPDATE ON orchard
FOR EACH ROW
EXECUTE FUNCTION set_updated_at_timestamp();


-- ────────────────────────────────────────────
--  2. tree
-- ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tree (
    tree_id        SERIAL             PRIMARY KEY,
    orchard_id     INTEGER            NOT NULL
                       REFERENCES orchard (orchard_id)
                       ON DELETE CASCADE,
    x_coordinate   DOUBLE PRECISION,
    y_coordinate   DOUBLE PRECISION,
    geom           GEOMETRY(POINT, 4326),
    age            INTEGER,
    status         tree_status_enum   NOT NULL DEFAULT 'healthy',
    current_stage  tree_stage_enum    NOT NULL DEFAULT 'dormant'
);

CREATE INDEX IF NOT EXISTS idx_tree_orchard_id ON tree (orchard_id);
CREATE INDEX IF NOT EXISTS idx_tree_geom       ON tree USING GIST (geom);


-- ────────────────────────────────────────────
--  3. pest
-- ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pest (
    pest_id          SERIAL                 PRIMARY KEY,
    name             VARCHAR(200)           NOT NULL,
    scientific_name  VARCHAR(300),
    attack_stage     pest_attack_stage_enum NOT NULL
);


-- ────────────────────────────────────────────
--  4. simulation_run
-- ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS simulation_run (
    id               SERIAL        PRIMARY KEY,
    simulation_id    SERIAL        UNIQUE NOT NULL,
    run_id           VARCHAR(100)  UNIQUE NOT NULL,

    -- Input parameters
    pest_type        pesttype      NOT NULL,
    orchard_id       VARCHAR(100),
    orchard_geojson  JSONB,
    bagged_tree_ids  JSONB,
    treatment_applications JSONB,
    simulation_mode  VARCHAR(50)   DEFAULT 'grid',
    hours            INTEGER       DEFAULT 48,

    -- Reproducibility
    random_seed      INTEGER,
    risk_threshold   DOUBLE PRECISION DEFAULT 0.7,

    -- Weather
    weather_source   VARCHAR(50)   DEFAULT 'synthetic',
    weather_data     JSONB,

    -- Results
    output_geojson   JSONB,
    request_payload  JSONB,
    response_payload JSONB,
    result_metadata  JSONB,
    time_series      JSONB,
    timesteps        JSONB,
    impact_assumptions JSONB,
    peak_risk        DOUBLE PRECISION,
    cells_at_risk    INTEGER,
    n_infested_final INTEGER,

    -- ERD fields
    start_date       TIMESTAMP,
    end_date         TIMESTAMP,
    description      TEXT,

    -- Timestamps
    started_at       TIMESTAMP     DEFAULT NOW(),
    completed_at     TIMESTAMP,
    duration_seconds DOUBLE PRECISION,

    -- Status
    status           VARCHAR(50)   DEFAULT 'running',
    error_message    TEXT
);

CREATE INDEX IF NOT EXISTS idx_simrun_run_id     ON simulation_run (run_id);
CREATE INDEX IF NOT EXISTS idx_simrun_orchard_id ON simulation_run (orchard_id);


-- ────────────────────────────────────────────
--  5. infestation_record
-- ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS infestation_record (
    infestation_id    SERIAL    PRIMARY KEY,
    tree_id           INTEGER   NOT NULL
                          REFERENCES tree (tree_id)
                          ON DELETE CASCADE,
    pest_id           INTEGER   NOT NULL
                          REFERENCES pest (pest_id)
                          ON DELETE CASCADE,
    -- NULL means this row is a field observation / ground-truth record,
    -- not generated by a simulation run.
    simulation_id     INTEGER
                          REFERENCES simulation_run (simulation_id)
                          ON DELETE CASCADE,
    record_date       TIMESTAMP,
    infected_status   BOOLEAN   DEFAULT FALSE,
    infestation_level NUMERIC(5, 2)
);

CREATE INDEX IF NOT EXISTS idx_infestation_tree_id       ON infestation_record (tree_id);
CREATE INDEX IF NOT EXISTS idx_infestation_pest_id       ON infestation_record (pest_id);
CREATE INDEX IF NOT EXISTS idx_infestation_simulation_id ON infestation_record (simulation_id);


-- ────────────────────────────────────────────
--  6. environmental_condition
-- ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS environmental_condition (
    condition_id   SERIAL           PRIMARY KEY,
    simulation_id  INTEGER          NOT NULL
                       REFERENCES simulation_run (simulation_id)
                       ON DELETE CASCADE,
    condition_date TIMESTAMP,
    temperature    NUMERIC(5, 2),
    humidity       NUMERIC(5, 2),
    rainfall       NUMERIC(7, 2),
    wind_speed     NUMERIC(5, 2)
);

CREATE INDEX IF NOT EXISTS idx_envcond_simulation_id ON environmental_condition (simulation_id);


-- ────────────────────────────────────────────
--  7. mango_stage
-- ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS mango_stage (
    stage_id       SERIAL                   PRIMARY KEY,
    simulation_id  INTEGER                  NOT NULL
                       REFERENCES simulation_run (simulation_id)
                       ON DELETE CASCADE,
    stage_date     TIMESTAMP,
    stage_status   mango_stage_status_enum  NOT NULL DEFAULT 'dormant'
);

CREATE INDEX IF NOT EXISTS idx_mangostage_simulation_id ON mango_stage (simulation_id);


-- ────────────────────────────────────────────
--  8. alert
-- ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS alert (
    id                  SERIAL        PRIMARY KEY,
    alert_id            VARCHAR(100)  UNIQUE NOT NULL,

    simulation_run_id   VARCHAR(100)  REFERENCES simulation_run (run_id),
    triggered_at        TIMESTAMP     DEFAULT NOW(),

    severity            alertseverity DEFAULT 'high',
    status              alertstatus   DEFAULT 'active',

    risk_value          DOUBLE PRECISION NOT NULL,
    affected_cells      JSONB,
    affected_tree_ids   JSONB,

    orchard_id          VARCHAR(100),
    zone_name           VARCHAR(100),
    centroid_lon        DOUBLE PRECISION,
    centroid_lat        DOUBLE PRECISION,

    message             TEXT,
    recommended_actions JSONB,
    suggested_simulation_params JSONB,

    email_sent          BOOLEAN       DEFAULT FALSE,
    email_sent_at       TIMESTAMP,
    sms_sent            BOOLEAN       DEFAULT FALSE,
    sms_sent_at         TIMESTAMP,

    acknowledged_by     VARCHAR(100),
    acknowledged_at     TIMESTAMP,
    resolved_at         TIMESTAMP,
    resolution_notes    TEXT,

    action_status       VARCHAR(50)   NOT NULL DEFAULT 'pending',
    action_assigned_to  VARCHAR(100),
    action_notes        TEXT,
    action_due_at       TIMESTAMP,
    action_completed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_alert_id       ON alert (alert_id);
CREATE INDEX IF NOT EXISTS idx_alert_status   ON alert (status);
CREATE INDEX IF NOT EXISTS idx_alert_severity ON alert (severity);


-- ────────────────────────────────────────────
--  9. weather_cache
-- ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS weather_cache (
    id                SERIAL        PRIMARY KEY,
    cache_key         VARCHAR(200)  UNIQUE NOT NULL,

    lon               DOUBLE PRECISION NOT NULL,
    lat               DOUBLE PRECISION NOT NULL,

    wind_speed_ms     DOUBLE PRECISION NOT NULL,
    wind_direction_deg DOUBLE PRECISION NOT NULL,
    temperature_c     DOUBLE PRECISION NOT NULL,
    humidity          DOUBLE PRECISION,

    raw_response      JSONB,

    fetched_at        TIMESTAMP     DEFAULT NOW(),
    expires_at        TIMESTAMP     NOT NULL,
    source            VARCHAR(50)   DEFAULT 'openweathermap'
);

CREATE INDEX IF NOT EXISTS idx_weather_cache_key ON weather_cache (cache_key);
