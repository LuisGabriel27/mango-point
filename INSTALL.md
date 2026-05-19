# MangoPoint Installation Guide

## Requirements

- Python 3.10+
- Node.js 18+ with npm
- PostgreSQL 14+ with PostGIS installed locally
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
DATABASE_URL=postgresql://postgres:your_password@localhost:5432/mangopoint
AUTH_SECRET_KEY=replace-with-a-long-random-secret
DEFAULT_ADMIN_PASSWORD=change-this-admin-password
```

Open-Meteo weather forecast calls do not require an API key.

## Database

For now, MangoPoint uses native local PostgreSQL/PostGIS for development. That
means each developer laptop needs its own PostgreSQL/PostGIS install until the
planned shared remote database is added.

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

Initialize tables and seed reference data:

```powershell
.\init_db.bat
```

If your virtual environment is already active, `python -m scripts.init_db` is equivalent.

The project currently uses schema initialization plus idempotent startup adjustments, not a full migration tool yet.

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
