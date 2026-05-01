# MangoPoint Installation Guide

## Requirements

- Python 3.10+
- PostgreSQL 14+ with PostGIS installed locally
- Git

## Setup

```bash
git clone <repository-url>
cd mango-point

python -m venv venv
venv\Scripts\activate

pip install -r requirements-api.txt
pip install -r dashboard/requirements-dashboard.txt

copy .env.example .env
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

```bash
python -m scripts.init_db
```

The project currently uses schema initialization plus idempotent startup adjustments, not a full migration tool yet.

## Run the App

Start the API:

```bash
python run_server.py --reload
```

Start the dashboard in another terminal:

```bash
python -m dashboard.app
```

API docs: `http://localhost:8000/docs`
Dashboard: `http://localhost:8050`

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

## Dashboard Configuration

The dashboard uses:

```env
MANGOPOINT_API_BASE=http://localhost:8000
```

Keep the API running before opening `http://localhost:8050`.

## Troubleshooting

- Database errors: confirm PostgreSQL is running and `DATABASE_URL` is correct.
- PostGIS errors: run `CREATE EXTENSION postgis;` in the `mangopoint` database.
- Auth errors: set `AUTH_SECRET_KEY` and use a non-default admin password.
- Import errors: activate the virtual environment and reinstall requirements.
- Dashboard connection issues: ensure the API is reachable on port `8000`.
- Historical validation weather errors: verify `data\hourly_weather.csv` has the required hourly rows and columns.
