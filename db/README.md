# MangoPoint Database — Integration Notes

## Overview

This directory contains the **consolidated** PostgreSQL + PostGIS database layer for MangoPoint.
All ORM models are defined in `db/models.py` — the single source of truth.

## Files

| File | Purpose |
|---|---|
| `models.py` | SQLAlchemy ORM models (9 tables, 7 enums) |
| `schema.sql` | Raw SQL schema (run once to create tables) |
| `import_geojson.py` | Import tree points from QGIS GeoJSON |
| `seed_pests.py` | Seed pest species (idempotent) |
| `migrations/` | Versioned local sync and cloud-backup migrations |
| `README.md` | This file |

## Setup

```bash
# 1. Create database + PostGIS extension
psql -U postgres -c "CREATE DATABASE mangopoint;"
psql -d mangopoint -c "CREATE EXTENSION IF NOT EXISTS postgis;"

# 2. Apply schema
psql -d mangopoint -f db/schema.sql

# 3. Import GeoJSON tree data
python -m db.import_geojson

# 4. Seed pest species
python -m db.seed_pests

# 5. Apply versioned sync/outbox migration and provision admin
python -m scripts.init_db
```

## Schema (12 application tables)

```
orchard ──< tree ──< infestation_record >── pest
                          │
              simulation_run ──< environmental_condition
              simulation_run ──< mango_stage
              simulation_run ──< alert

weather_cache (standalone)
```

- **orchard** — orchard metadata
- **tree** — spatial data (PostGIS `geom` + `x/y_coordinate`)
- **pest** — pest species
- **simulation_run** — simulation run history & results
- **infestation_record** — per-tree infestation events
- **environmental_condition** — weather inputs per simulation
- **mango_stage** — phenological stage records
- **alert** — risk alert log
- **weather_cache** — weather API response cache
- **sync_outbox** — transactional local-to-cloud replication queue
- **sync_state** — last synchronization status and checkpoint
- **orchard_asset** — local/cloud asset manifest

`weather_cache` is intentionally not replicated. Orchard asset files and their
manifest are local-only. The sync triggers cover durable application tables
and enqueue events in the same transaction as the original write; the cloud
worker performs idempotent upserts for database rows only.

## Backward Compatibility

The file `api/models/database.py` is a re-export shim:
```python
from db.models import *
TreeRegistry = Tree          # legacy alias
PestObservation = InfestationRecord  # legacy alias
```

This ensures any code using `from ..models.database import X` continues to work.
