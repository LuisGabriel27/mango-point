-- Short-lived, hashed verification codes for password recovery.

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
