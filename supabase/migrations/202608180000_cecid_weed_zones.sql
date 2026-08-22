-- Mirror local orchard weed-habitat persistence in Supabase.
ALTER TABLE IF EXISTS orchard
ADD COLUMN IF NOT EXISTS cecid_weed_zones JSONB NOT NULL DEFAULT '[]'::jsonb;
