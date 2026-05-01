# MangoPoint Dashboard

Dash and Plotly dashboard for the MangoPoint backend.

## Quick Start

Start the API first:

```bash
cd mango-point
venv\Scripts\activate
python run_server.py --reload
```

Start the dashboard in another terminal:

```bash
cd mango-point
venv\Scripts\activate
python -m dashboard.app
```

Backend: `http://localhost:8000`
Dashboard: `http://localhost:8050`

## Configuration

The dashboard reads the API URL from `.env` or the process environment:

```env
MANGOPOINT_API_BASE=http://localhost:8000
DASHBOARD_ALERT_REFRESH_SECONDS=120
```

It does not need direct database access. Authentication, orchard data, simulations, alerts, observations, validation, and monitoring are all accessed through the API.

## Included Views

- Simulation controls and risk playback map
- Orchard switching and tree-level inspection
- Weather-aware alerts and monitoring
- Decision support summary and action plan
- Treatment/spray scenario controls
- Field observation submission
- Live evaluation
- Historical validation results and charts

## Folder Layout

| Path | Purpose |
|---|---|
| `dashboard/app.py` | Main Dash application |
| `dashboard/requirements-dashboard.txt` | Dashboard dependencies |
| `dashboard/tools/` | One-off maintenance helpers for the dashboard |

## Notes

- Keep the API running before loading the dashboard.
- If the dashboard cannot sign in or load data, check `MANGOPOINT_API_BASE`, API logs, and browser network errors.
- `dashboard/app.py` is still a large module and is a known refactor target.
