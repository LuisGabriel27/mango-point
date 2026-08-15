-- Orchard files and their local manifest remain local-only.
DROP TRIGGER IF EXISTS trg_orchard_asset_sync ON orchard_asset;

UPDATE sync_outbox
SET synced_at = COALESCE(synced_at, NOW()),
    last_error = NULL
WHERE entity_type = 'orchard_asset'
  AND synced_at IS NULL;

UPDATE orchard_asset
SET sync_status = 'local_only',
    updated_at = NOW()
WHERE sync_status <> 'local_only';
