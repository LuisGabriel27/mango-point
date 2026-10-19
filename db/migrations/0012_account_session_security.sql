-- Session slots are local to the authoritative API database and are not backed up.
CREATE TABLE IF NOT EXISTS auth_session (
    session_id VARCHAR(36) PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES user_account(user_id) ON DELETE CASCADE,
    credential_stamp VARCHAR(64) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    revoked_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_auth_session_user ON auth_session(user_id);
CREATE INDEX IF NOT EXISTS idx_auth_session_expires ON auth_session(expires_at);

ALTER TABLE password_reset_challenge ADD COLUMN IF NOT EXISTS purpose VARCHAR(20) NOT NULL DEFAULT 'reset';
ALTER TABLE password_reset_challenge ADD COLUMN IF NOT EXISTS email_snapshot VARCHAR(255);
ALTER TABLE password_reset_challenge ADD COLUMN IF NOT EXISTS credential_stamp VARCHAR(64);
