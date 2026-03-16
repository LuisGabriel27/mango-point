# MangoPoint Installation Guide

## Requirements

- Python 3.10+
- PostgreSQL 14+ with PostGIS
- Git

## Setup

```bash
git clone <repository-url>
cd capstone/mangopoint

python -m venv venv
venv\Scripts\activate

pip install -r requirements-api.txt
pip install -r dashboard/requirements-dashboard.txt

copy .env.example .env
```

Set at least:

```env
DATABASE_URL=postgresql://postgres:your_password@localhost:5432/mangopoint
```

## Database

Create the database and enable PostGIS:

```sql
CREATE DATABASE mangopoint;
\c mangopoint
CREATE EXTENSION postgis;
```

Initialize tables:

```bash
python -m scripts.init_db
```

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

```bash
python -m scripts.run_validation
python -m scripts.run_validation --data-summary
```

## Troubleshooting

- Database errors: confirm PostgreSQL is running and `DATABASE_URL` is correct.
- PostGIS errors: run `CREATE EXTENSION postgis;` in the `mangopoint` database.
- Import errors: activate the virtual environment and reinstall requirements.
- Dashboard connection issues: ensure the API is reachable on port `8000`.
