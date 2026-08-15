# MangoPoint Installation Guide

## Requirements

- Python 3.10+
- Node.js 18+ with npm
- Docker Desktop (for the local PostgreSQL/PostGIS container)
- Git

## Setup

```bash
git clone <repository-url>
cd <project-folder>

python -m venv .venv
.\.venv\Scripts\activate

python -m pip install -r requirements-api.txt

copy .env.example .env

cd frontend
npm install
cd ..
```

Set at least:

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:55432/mangopoint
AUTH_SECRET_KEY=replace-with-a-long-random-secret
DEFAULT_ADMIN_PASSWORD=change-this-admin-password
```

Open-Meteo weather forecast calls do not require an API key.

## Database

MangoPoint uses Dockerized PostgreSQL/PostGIS locally. The local database is the
authoritative write target; Supabase is an optional server-side cloud backup.

Start the database:

```powershell
docker compose up -d
```

The default Docker credentials match `.env.example`:

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:55432/mangopoint
```

The existing native PostgreSQL setup remains supported for legacy installations.

Create the database and enable PostGIS:

```sql
CREATE DATABASE mangopoint;
\c mangopoint
CREATE EXTENSION postgis;
```

On Windows, the helper script can check the native install, create the database,
enable PostGIS, and apply the base schema:

```powershell
$env:PGPASSWORD="your_postgres_password"
.\db\setup_db.ps1 -PgPort 5432
```

If you use that legacy native setup instead of Docker, set `DATABASE_URL` back
to port `5432` before running the API.

Initialize tables, sync triggers, and the default admin account:

```powershell
.\init_db.bat
```

If your virtual environment is already active, `python -m scripts.init_db` is equivalent.

The versioned sync migration is applied by `scripts.init_db`. The original
domain schema remains in `db/schema.sql`; future schema changes should be added
as ordered files under `db/migrations/` and mirrored under `supabase/migrations/`.

For cloud database backup, configure the server-side Supabase values from `.env.example`,
then run `.\sync_cloud.bat` once to verify connectivity. Orchard files remain
local-only. Schedule the same command every two hours for recovery-point
protection.

## Run the App

Quick Windows start:

```powershell
.\start_dev.bat
```

Start the API:

```powershell
.\start_api.bat
```

If PowerShell says `uvicorn.exe` was blocked by Application Control, start the
same server from a new VS Code terminal so the repo-local `uvicorn.cmd` wrapper
is first on `Path`:

```powershell
uvicorn api.main:app --reload --port 8000
```

You can also start the same server through Python directly:

```powershell
python run_server.py --reload --port 8000
```

You can also use the Windows helper:

```powershell
.\start_api.bat
```

Start the frontend in another terminal:

```powershell
.\start_frontend.bat
```

API docs: `http://localhost:8000/docs`
Frontend: `http://localhost:3000`

## Validation

Quick validation:

```bash
python -m scripts.run_validation --data-summary
python -m scripts.run_validation --max-cases 5 --monte-carlo 5 --bootstrap 0 --no-export
```

Calibrated historical-weather validation:

```bash
python -m scripts.run_validation --historical-weather-csv data\hourly_weather.csv --require-historical-weather --test-years 2025
```

`--require-historical-weather` exits before simulation if any selected validation case would fall back to synthetic weather.

## Frontend Configuration

Local frontend development uses the Vite proxy in `frontend/vite.config.js`, so API requests go to `http://localhost:8000`.
For a static build or custom API host, create `frontend/.env` from `frontend/.env.example` and set:

```env
VITE_API_BASE=http://localhost:8000
```

Keep the API running before opening `http://localhost:3000`.

## Troubleshooting

- Database errors: confirm PostgreSQL is running and `DATABASE_URL` is correct.
- PostGIS errors: run `CREATE EXTENSION postgis;` in the `mangopoint` database.
- Auth errors: set `AUTH_SECRET_KEY` and use a non-default admin password.
- Import errors: activate the virtual environment and reinstall requirements.
- `uvicorn.exe` blocked on Windows: close the old terminal and open a new VS Code terminal; or run `$env:Path = "$PWD;$env:Path"` once in the old terminal; or use `.\start_api.bat`.
- Frontend dependency errors: run `cd frontend` then `npm install`.
- Frontend connection issues: ensure the API is reachable on port `8000`.
- Historical validation weather errors: verify `data\hourly_weather.csv` has the required hourly rows and columns.
