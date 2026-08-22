-- Persist adult-only Cecid weed habitat independently of tree GeoJSON.
ALTER TABLE IF EXISTS orchard
ADD COLUMN IF NOT EXISTS cecid_weed_zones JSONB NOT NULL DEFAULT '[]'::jsonb;
