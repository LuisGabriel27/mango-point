-- Supabase mirror of local migration 0008_release1_zones_and_observations.sql.

BEGIN;

SET search_path = public, extensions, gis;

ALTER TABLE IF EXISTS orchard
ADD COLUMN IF NOT EXISTS management_zones JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE IF EXISTS tree
ADD COLUMN IF NOT EXISTS external_id VARCHAR(150);

CREATE UNIQUE INDEX IF NOT EXISTS uq_tree_orchard_external_id
    ON tree (orchard_id, external_id);

DO $$
BEGIN
    IF to_regtype('tree_status_enum') IS NOT NULL THEN
        ALTER TYPE tree_status_enum ADD VALUE IF NOT EXISTS 'history_infected';
        ALTER TYPE tree_status_enum ADD VALUE IF NOT EXISTS 'suspect';
    END IF;
END $$;

ALTER TABLE IF EXISTS infestation_record
ADD COLUMN IF NOT EXISTS tree_external_id VARCHAR(150),
ADD COLUMN IF NOT EXISTS observation_status VARCHAR(30),
ADD COLUMN IF NOT EXISTS affected_count INTEGER,
ADD COLUMN IF NOT EXISTS inspected_count INTEGER,
ADD COLUMN IF NOT EXISTS observation_method VARCHAR(100),
ADD COLUMN IF NOT EXISTS observer_id VARCHAR(200),
ADD COLUMN IF NOT EXISTS notes TEXT,
ADD COLUMN IF NOT EXISTS image_url VARCHAR(1000),
ADD COLUMN IF NOT EXISTS observation_lon DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS observation_lat DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS verification_run_id VARCHAR(100),
ADD COLUMN IF NOT EXISTS forecast_risk DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS forecast_lead_hours INTEGER,
ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT NOW();

UPDATE infestation_record
SET observation_status = CASE WHEN infected_status THEN 'present' ELSE 'absent' END
WHERE simulation_id IS NULL AND observation_status IS NULL;

UPDATE infestation_record record
SET tree_external_id = COALESCE(tree.external_id, tree.tree_id::text)
FROM tree
WHERE record.tree_id = tree.tree_id
  AND record.tree_external_id IS NULL;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_infestation_observation_status' AND conrelid = 'infestation_record'::regclass) THEN
        ALTER TABLE infestation_record ADD CONSTRAINT ck_infestation_observation_status
        CHECK (observation_status IS NULL OR observation_status IN ('present', 'absent', 'not_inspected'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_infestation_counts' AND conrelid = 'infestation_record'::regclass) THEN
        ALTER TABLE infestation_record ADD CONSTRAINT ck_infestation_counts
        CHECK (affected_count IS NULL OR inspected_count IS NULL OR affected_count <= inspected_count);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_infestation_forecast_risk' AND conrelid = 'infestation_record'::regclass) THEN
        ALTER TABLE infestation_record ADD CONSTRAINT ck_infestation_forecast_risk
        CHECK (forecast_risk IS NULL OR (forecast_risk >= 0 AND forecast_risk <= 1));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_infestation_tree_external_id
    ON infestation_record (tree_external_id);
CREATE INDEX IF NOT EXISTS idx_infestation_verification_run_id
    ON infestation_record (verification_run_id);

RESET search_path;

COMMIT;
