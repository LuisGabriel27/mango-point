-- Short-lived, hashed verification codes for password recovery.

BEGIN;

SET search_path = public, extensions, gis;

CREATE TABLE IF NOT EXISTS password_reset_challenge (
    challenge_id VARCHAR(36) PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES user_account (user_id) ON DELETE CASCADE,
    code_hash VARCHAR(255) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    expires_at TIMESTAMP NOT NULL,
    consumed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_password_reset_challenge_user
    ON password_reset_challenge (user_id);

CREATE INDEX IF NOT EXISTS idx_password_reset_challenge_expires
    ON password_reset_challenge (expires_at);

-- Reset-code hashes are server-only and must never be exposed by PostgREST.
ALTER TABLE password_reset_challenge ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL PRIVILEGES ON TABLE password_reset_challenge FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL PRIVILEGES ON TABLE password_reset_challenge FROM authenticated;
    END IF;
END $$;

RESET search_path;

COMMIT;
