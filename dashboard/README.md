# MangoPoint Dashboard

Dash and Plotly dashboard for the MangoPoint backend.

## Quick Start

```bash
cd mangopoint
pip install -r dashboard/requirements-dashboard.txt

python run_server.py
python -m dashboard.app
```

Backend: `http://localhost:8000`  
Dashboard: `http://localhost:8050`

## Folder Layout

| Path | Purpose |
|---|---|
| `dashboard/app.py` | Main Dash application |
| `dashboard/requirements-dashboard.txt` | Dashboard dependencies |
| `dashboard/tools/` | One-off maintenance helpers for the dashboard |

## Notes

- The dashboard talks to the API over HTTP and does not need direct database access.
- `API_BASE` and other UI defaults are defined near the top of `dashboard/app.py`.
