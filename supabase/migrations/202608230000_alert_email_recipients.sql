-- Admin-managed recipients for off-site pest alert emails.
-- Protected cloud replication is enabled by migration 202608240001.

BEGIN;

SET search_path = public, extensions, gis;

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

DROP TRIGGER IF EXISTS trg_alert_email_recipient_set_updated_at
    ON alert_email_recipient;
CREATE TRIGGER trg_alert_email_recipient_set_updated_at
BEFORE UPDATE ON alert_email_recipient
FOR EACH ROW EXECUTE FUNCTION set_updated_at_timestamp();

DROP TRIGGER IF EXISTS trg_alert_email_recipient_sync
    ON alert_email_recipient;

RESET search_path;

COMMIT;
