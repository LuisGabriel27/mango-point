# MangoPoint

MangoPoint is a GIS-based pest spread forecasting web application for mango orchards. It combines a FastAPI backend, a React/Vite frontend, cellular and tree-graph simulation modes, weather-driven biological gates, alerting, decision support, and historical validation against BPI Guimaras pest monitoring data.

## Current Capabilities

- Pest spread simulation for Cecid Fly and Fruit Fly.
- Grid and tree-graph simulation modes, including real crown-width/crown-radius handling.
- Weather-aware biological triggers using Open-Meteo forecast data, manual weather blocks, synthetic fallback weather, and historical weather CSVs for validation.
- Cecid-specific fixed soil sources, short-lived adult cohorts, and persistent Weed Habitat relay zones with a strict 15 m hourly movement limit.
- Multi-orchard API foundation and frontend orchard switching.
- Alerts for high-risk simulation output and orchard-aware scheduled gate monitoring.
- Notification/action workflow for alerts.
- Decision support action plans and treatment/spray scenario controls.
- Field observations and evaluation endpoints.
- Historical validation against BPI Guimaras monitoring records, including calibration/testing splits, confidence intervals, and historical weather coverage reporting.
- Manual field validation protocol for checking current forecasts against later orchard inspections.

## Project Layout

| Path | Purpose |
|---|---|
| `api/` | FastAPI app, routes, services, and API-facing schemas |
| `core/` | Simulation engine, configuration, grid logic, biological rules |
| `spatial/` | GIS conversion, raster helpers, orchard coordinates |
| `utils/` | Weather ingestion, evaluation, visualization, decision support |
| `validation/` | Historical validation workflows and reporting |
| `frontend/` | React/Vite UI for simulation, monitoring, validation, and review |
| `db/` | Database schema, ORM models, and import helpers |
| `scripts/` | Entry points for database init, API startup, and validation runs |
| `data/` | GIS inputs, BPI pest data, and historical weather data |
| `outputs/` | Generated simulation and validation outputs |

## Quick Start

Run the local PostgreSQL/PostGIS database in Docker. The FastAPI service remains
the only application data boundary. When Supabase credentials are configured,
local durable writes are queued for cloud backup every two hours.

```powershell
cd <project-folder>

docker compose up -d
.\setup_windows.bat
.\init_db.bat
.\start_dev.bat
```

On Windows machines with Application Control enabled, run the API through
Python instead of the `uvicorn.exe` console launcher:

```powershell
uvicorn api.main:app --reload --port 8000
# or
python run_server.py --reload --port 8000
# or
python -m uvicorn api.main:app --reload --port 8000
```

If an already-open VS Code terminal still resolves to the blocked global
`uvicorn.exe`, either close that terminal and open a new one, or run this once
in the already-open terminal:

```powershell
$env:Path = "$PWD;$env:Path"
```

New project terminals put this repo first on `Path`, so `uvicorn` resolves to
`uvicorn.cmd`.

If you prefer separate terminals instead of `.\start_dev.bat`:

```powershell
.\start_api.bat
```

```powershell
.\start_frontend.bat
```

API docs: `http://localhost:8000/docs`
Frontend: `http://localhost:3000`

Default local login after database initialization:

```text
username: admin
password: change-this-admin-password
```

Change `DEFAULT_ADMIN_PASSWORD` in `.env` before a shared demo.

Manual setup, if you do not want to use the Windows helper:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r requirements-api.txt
copy .env.example .env

cd frontend
npm install
cd ..

python -m scripts.check_setup
.\init_db.bat
.\start_api.bat
```

Then run the frontend in another terminal:

```powershell
.\start_frontend.bat
```

## Environment

Copy `.env.example` to `.env` and set at least:

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:55432/mangopoint
AUTH_SECRET_KEY=replace-with-a-long-random-secret
DEFAULT_ADMIN_PASSWORD=change-this-admin-password
```

Open-Meteo is used for weather forecasts and does not require an API key.
For local Docker, the default connection is:

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:55432/mangopoint
```

Docker maps its database to host port `55432` by default so it does not silently
compete with an existing native PostgreSQL installation on `5432`. Set
`POSTGRES_PORT` and update `DATABASE_URL` together if you want another port.

The setup command applies the versioned files in `db/migrations/` after the
domain schema. The migration adds the transactional sync outbox, synchronization
state. Orchard files remain local-only and are not uploaded to Supabase.

## Supabase cloud backup

Supabase is used as a server-side backup target. Do not put these values in
`frontend/.env` or expose them through Vite:

```env
SUPABASE_DATABASE_URL=postgresql://...
CLOUD_SYNC_ENABLED=true
CLOUD_SYNC_ASSETS=false
CLOUD_SYNC_INTERVAL_SECONDS=7200
```

The API starts a best-effort two-hour scheduler when the cloud database URL is
configured. You can also run a manual batch:

```powershell
.\sync_cloud.bat
```

The protected API endpoints are `GET /sync/status` and `POST /sync/run`.
For a machine-wide automatic backup, schedule `sync_cloud.bat` in Windows Task
Scheduler every two hours. If Supabase is unavailable, local writes continue
and remain in the outbox for retry.

To inspect or restore a cloud copy:

```powershell
.\.venv\Scripts\python.exe -m scripts.sync_cloud --once
.\.venv\Scripts\python.exe -m scripts.restore_from_supabase --dry-run
.\.venv\Scripts\python.exe -m scripts.restore_from_supabase
```

The restore command must only be run against a replacement or intentionally
empty local database. It restores database rows in dependency order. Orchard
files must be restored separately from your local file backup because they are
not stored in Supabase.

## Cecid Fly Weed Habitat

Select `Weed Habitat` in the Live Map Zone Editor to draw persistent orchard
polygons and classify them as Sparse, Moderate, or Dense. Every draw, label or
density edit, undo, and deletion is saved through the orchard API. The map shows
Saving, Saved, or Error with a retry action; clearing all weed zones requires
confirmation. The bundled BPI map is registered once as `default-orchard`, so
its weed zones use the same persistence path as uploaded orchards.

Weed polygons are provisional adult shelter and short-hop relay assumptions.
They do not create Cecid flies, strengthen soil emergence, act as alternate
hosts, or create another generation. The relay efficiencies (0.60/0.80/1.00)
require BPI field calibration. Legacy `cecid_emergence_zones` remain available
only for exact historical replay and are not converted into orchard weeds.

For Cecid wind controls, values remain in m/s. Gentle wind from 1–5 km/h
(0.28–1.39 m/s) can assist a movement edge downwind by up to 35%. Wind above
5 km/h progressively lowers adult survival, but never allows movement farther
than 15 m in one eligible dawn/dusk hour.

## Validation

Basic historical validation:

```bash
python -m scripts.run_validation
python -m scripts.run_validation --data-summary
```

Defense-oriented calibrated validation using the bundled Open-Meteo historical hourly archive:

```bash
python -m scripts.run_validation --historical-weather-csv data\hourly_weather.csv --require-historical-weather --test-years 2025
```

Useful quick validation command:

```bash
python -m scripts.run_validation --historical-weather-csv data\hourly_weather.csv --require-historical-weather --test-years 2025 --monte-carlo 5 --bootstrap 0 --no-export
```

See [validation/README.md](validation/README.md) for calibration/testing splits, weather coverage, confidence intervals, and the manual field validation protocol.

## Data Notes

- `data/guimaras_pest_data_2022_2025.csv` contains monthly BPI pest monitoring records.
- `data/hourly_weather.csv` is a normalized Open-Meteo historical hourly archive for 2022-2025 at the orchard coordinates.
- `data/open_meteo_hourly_raw.csv` preserves the raw Open-Meteo CSV response for traceability.
- Open-Meteo historical data is model/reanalysis weather, not an official PAGASA station observation file.

## Safe Claims

Good claims:

- The system simulates pest spread using weather, phenology, orchard layout, and pest-specific biological rules.
- Historical validation compares simulations against BPI Guimaras monitoring records.
- Calibrated validation can use a holdout year and historical hourly weather coverage checks.
- Manual field validation can be used to test current forecasts against later orchard observations.

Avoid overclaiming:

- Do not call this a proven final forecasting model without additional field trials.
- BPI pest records are monthly aggregate records, not tree-level spread labels.
- Open-Meteo historical weather is not the same as raw PAGASA station data.
- Treatment/spray controls are scenario factors, not pesticide product or dosage recommendations.

## Development Checks

```bash
pytest -q
python -m py_compile api\services\simulation_service.py validation\weather_scenarios.py scripts\check_setup.py
cd frontend
npm run build
```

## Notes

- Runnable helpers live in `scripts/`.
- `run_server.py` is the top-level convenience entry point for starting the API.
- The frontend talks to the API through the Vite dev proxy during local development.
