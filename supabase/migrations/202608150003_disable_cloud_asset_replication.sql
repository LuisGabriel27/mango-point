-- Orchard files and their local manifest are not part of cloud backup.
DROP TRIGGER IF EXISTS trg_orchard_asset_sync ON orchard_asset;

DELETE FROM sync_outbox
WHERE entity_type = 'orchard_asset';
