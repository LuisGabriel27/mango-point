-- Preserve intentional empty admin recipient lists after a hard delete.
-- Cloud replication is enabled separately by 0007.

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
