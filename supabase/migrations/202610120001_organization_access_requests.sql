-- Public inquiry intake is written through FastAPI. Reviewing a request does
-- not create an account, an orchard or a subscription entitlement.
CREATE TABLE IF NOT EXISTS access_request (
    request_id VARCHAR(36) PRIMARY KEY,
    reference VARCHAR(20) NOT NULL UNIQUE,
    payload_hash VARCHAR(64) NOT NULL,
    client_hash VARCHAR(64) NOT NULL,
    organization VARCHAR(200) NOT NULL,
    sector VARCHAR(30) NOT NULL,
    contact_name VARCHAR(150) NOT NULL,
    email VARCHAR(254) NOT NULL,
    phone VARCHAR(50) NOT NULL DEFAULT '',
    location VARCHAR(200) NOT NULL,
    orchard_count INTEGER,
    interest VARCHAR(30) NOT NULL,
    message TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'new',
    notes TEXT NOT NULL DEFAULT '',
    version INTEGER NOT NULL DEFAULT 1,
    consent_version VARCHAR(50) NOT NULL DEFAULT 'access-inquiry-v1',
    reviewed_by_user_id INTEGER REFERENCES user_account(user_id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_access_request_status CHECK (status IN ('new', 'reviewing', 'approved', 'closed')),
    CONSTRAINT ck_access_request_version CHECK (version >= 1),
    CONSTRAINT ck_access_request_orchards CHECK (orchard_count IS NULL OR orchard_count BETWEEN 0 AND 100000)
);

CREATE INDEX IF NOT EXISTS idx_access_request_status_created ON access_request(status, created_at);
CREATE INDEX IF NOT EXISTS idx_access_request_client_created ON access_request(client_hash, created_at);

DROP TRIGGER IF EXISTS trg_access_request_sync ON access_request;
CREATE TRIGGER trg_access_request_sync
AFTER INSERT OR UPDATE OR DELETE ON access_request
FOR EACH ROW EXECUTE FUNCTION enqueue_mangopoint_sync_event('request_id');

INSERT INTO sync_outbox (entity_type, entity_key, operation)
SELECT 'access_request', request_id, 'upsert' FROM access_request source
WHERE NOT EXISTS (
    SELECT 1 FROM sync_outbox queued
    WHERE queued.entity_type = 'access_request'
      AND queued.entity_key = source.request_id
      AND queued.operation = 'upsert'
      AND queued.synced_at IS NULL
);

-- No browser-facing Supabase policies: the FastAPI service is the data
-- boundary and its configured database role performs durable synchronization.
ALTER TABLE access_request ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON access_request FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL ON access_request FROM authenticated;
    END IF;
END $$;
