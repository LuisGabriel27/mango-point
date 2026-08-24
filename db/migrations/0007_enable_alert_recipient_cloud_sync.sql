-- Replicate managed alert recipients and their authoritative-list state to
-- the configured Supabase backup database.

DROP TRIGGER IF EXISTS trg_alert_email_recipient_sync ON alert_email_recipient;
CREATE TRIGGER trg_alert_email_recipient_sync
AFTER INSERT OR UPDATE OR DELETE ON alert_email_recipient
FOR EACH ROW EXECUTE FUNCTION enqueue_mangopoint_sync_event('recipient_id');

DROP TRIGGER IF EXISTS trg_alert_email_recipient_state_sync
    ON alert_email_recipient_state;
CREATE TRIGGER trg_alert_email_recipient_state_sync
AFTER INSERT OR UPDATE OR DELETE ON alert_email_recipient_state
FOR EACH ROW EXECUTE FUNCTION enqueue_mangopoint_sync_event('state_id');

-- Queue rows that existed before cloud replication was enabled.
INSERT INTO sync_outbox (entity_type, entity_key, operation)
SELECT 'alert_email_recipient', recipient_id::TEXT, 'upsert'
FROM alert_email_recipient source
WHERE NOT EXISTS (
    SELECT 1 FROM sync_outbox queued
    WHERE queued.entity_type = 'alert_email_recipient'
      AND queued.entity_key = source.recipient_id::TEXT
      AND queued.operation = 'upsert'
      AND queued.synced_at IS NULL
);

INSERT INTO sync_outbox (entity_type, entity_key, operation)
SELECT 'alert_email_recipient_state', state_id::TEXT, 'upsert'
FROM alert_email_recipient_state source
WHERE NOT EXISTS (
    SELECT 1 FROM sync_outbox queued
    WHERE queued.entity_type = 'alert_email_recipient_state'
      AND queued.entity_key = source.state_id::TEXT
      AND queued.operation = 'upsert'
      AND queued.synced_at IS NULL
);
