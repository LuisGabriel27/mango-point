# MangoPoint

GIS-based pest risk simulation for mango orchards, with a FastAPI backend, a Dash dashboard, and a historical validation pipeline.

## Project Layout

| Path | Purpose |
|---|---|
| `api/` | FastAPI app, routes, services, and API-facing schemas |
| `core/` | Simulation engine, configuration, grid logic, biological rules |
| `spatial/` | GIS conversion, raster helpers, orchard coordinates |
| `utils/` | Weather ingestion, evaluation, visualization, decision support |
| `validation/` | Historical validation workflows and reporting |
| `dashboard/` | Dash UI for simulation, monitoring, and review |
| `db/` | Database schema, ORM models, and import helpers |
| `scripts/` | Entry points for database init, API startup, and validation runs |
| `data/` | GIS inputs and historical datasets |
| `outputs/` | Generated simulation and validation outputs |

## Quick Start

```bash
cd mangopoint

python -m venv venv
venv\Scripts\activate

pip install -r requirements-api.txt
pip install -r dashboard/requirements-dashboard.txt

copy .env.example .env
python -m scripts.init_db
python run_server.py --reload
```

In a second terminal:

```bash
cd mangopoint
venv\Scripts\activate
python -m dashboard.app
```

API docs: `http://localhost:8000/docs`  
Dashboard: `http://localhost:8050`

## Validation

```bash
python -m scripts.run_validation
python -m scripts.run_validation --pest-type fruitfly
python -m scripts.run_validation --data-summary
```

## Main Features

- Cellular automata pest dispersal simulation for Cecid Fly and Fruit Fly
- FastAPI endpoints for simulation, weather, alerts, observations, monitoring, and validation
- Dash dashboard for risk maps, playback, alerts, and tree management
- PostgreSQL/PostGIS-backed data model
- Historical validation against BPI Guimaras monitoring data

## Notes

- The old root-level module shims were removed. Import from `core`, `spatial`, `utils`, `validation`, and `api` directly.
- Runnable helpers now live in `scripts/`.
- `run_server.py` is the top-level convenience entry point for starting the API.
