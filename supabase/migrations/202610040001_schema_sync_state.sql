-- Private metadata for the consolidated schema updater. The hash is recorded
-- only after all schema statements succeed in the same transaction.
CREATE TABLE IF NOT EXISTS public.mangopoint_schema_state (
    schema_key VARCHAR(100) PRIMARY KEY,
    schema_hash VARCHAR(64) NOT NULL,
    applied_at TIMESTAMP NOT NULL DEFAULT NOW()
);

ALTER TABLE public.mangopoint_schema_state ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON TABLE public.mangopoint_schema_state FROM PUBLIC;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL PRIVILEGES ON TABLE public.mangopoint_schema_state FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL PRIVILEGES ON TABLE public.mangopoint_schema_state FROM authenticated;
    END IF;
END $$;
