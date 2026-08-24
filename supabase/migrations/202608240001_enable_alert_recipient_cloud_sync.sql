-- Enable protected cloud backup for alert recipient contact records.

BEGIN;

SET search_path = public, extensions, gis;

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

-- These contact tables are backup-only through the server-side PostgreSQL
-- connection. Do not expose them through Supabase's anon/authenticated API.
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

DROP TRIGGER IF EXISTS trg_alert_email_recipient_sync ON alert_email_recipient;
CREATE TRIGGER trg_alert_email_recipient_sync
AFTER INSERT OR UPDATE OR DELETE ON alert_email_recipient
FOR EACH ROW EXECUTE FUNCTION enqueue_mangopoint_sync_event('recipient_id');

DROP TRIGGER IF EXISTS trg_alert_email_recipient_state_sync
    ON alert_email_recipient_state;
CREATE TRIGGER trg_alert_email_recipient_state_sync
AFTER INSERT OR UPDATE OR DELETE ON alert_email_recipient_state
FOR EACH ROW EXECUTE FUNCTION enqueue_mangopoint_sync_event('state_id');

RESET search_path;

COMMIT;
