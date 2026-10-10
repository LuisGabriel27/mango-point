# MangoPoint

MangoPoint is a GIS-based pest spread forecasting web application for mango orchards. It combines a FastAPI backend, a React/Vite frontend, cellular automata (CA) and tree-to-tree graph simulation modes, weather-driven biological gates, alerting, decision support, and historical comparison against BPI Guimaras pest monitoring data.

The pest scope is **fruit-attacking Cecid** and **Oriental Fruit Fly
(*Bactrocera dorsalis*)**. The current reviewed model is
`2026.10-source-progression-v17`; its source rules and remaining assumptions are
documented in the [v17 model review](docs/v17-model-readiness-review.md).
The React Joyride tutorial described below is a planned upgrade.

## Current Capabilities

- Pest spread simulation for fruit-attacking Cecid and Oriental Fruit Fly.
- Grid and tree-graph simulation modes, including real crown-width/crown-radius handling.
- Weather-aware biological triggers using Open-Meteo forecast data, manual weather blocks, synthetic fallback weather, and historical weather CSVs for validation.
- Cecid-specific soil sources, finite short-lived adult cohorts and laying capacity, moisture/light/rain gates, and persistent Weed Habitat relay zones. Local movement has an assumed 15 m hourly limit; outside pressure is a separate directional exposure proxy.
- Fruit Fly initial adult source pressure is retained separately from new fruit infestation. New fruit damage does not create another adult source within the same forecast.
- Explicit source-presence scenarios, bagging/treatment factors, and 1, 5 or 9 repeated realizations with separate frequency and one-run views.
- Multi-orchard API foundation and frontend orchard switching.
- Alerts for high-risk simulation output and orchard-aware scheduled gate monitoring.
- Notification/action workflow for alerts.
- Decision support action plans and treatment/spray scenario controls.
- Field observations and evaluation endpoints.
- Saved simulation History, input templates, Excel exports, and printable reports with recorded model/input assumptions.
- Historical validation against BPI Guimaras monitoring records, including calibration/testing splits, confidence intervals, and historical weather coverage reporting.
- Manual field validation protocol for checking current forecasts against later orchard inspections.

## Application Workflow

After signing in, use the workspace's **Setup → Simulate → Results → Verify**
sequence. The dashboard also provides Live Map, Overview, Crop Impact,
Surveillance and History views.

1. **Setup:** Select an orchard and inspect its tree statuses, host stages and
   source assumptions. Choose Live Forecast or Custom Weather. Distinguish
   temporary scenario edits from edits applied to the saved orchard.
2. **Simulate:** Select the pest, CA or Tree Graph, duration, repeated-run count,
   and applicable source, neighbor and treatment settings. Review the inputs,
   then press **Run Simulation**.
3. **Results:** Inspect the map, legend, tree details, hourly playback and
   summaries. Across runs shows simulated infestation frequency; One run and
   playback show a representative realization. These are modeled outcomes.
4. **History and reports:** Check that the completed run appears in History.
   **Load Result** opens the saved output; **Use as Template** restores inputs
   for a new run. Export Excel or print a report, checking its orchard, model
   version and final/displayed reporting hour.
5. **Verify:** Record an actual orchard inspection with the correct tree, pest,
   date and method. Present, Absent and Not inspected are distinct records;
   simulated infestation must not be saved as an observed finding.

Use the [66-case manual workflow test plan](docs/manual-workflow-test-plan.md),
[results sheet](docs/manual-workflow-test-results.csv) and
[bug log](docs/manual-workflow-bug-log.csv) for the full rehearsal. The starting
test sheet contains Not run cases; preparing it does not establish a pass.

## Planned Demo and Tutorial: React Joyride

**Status: documentation prepared; implementation has not started.**
`react-joyride` is not currently a frontend dependency. This documentation step
does not install the package or change React components, styles or application
behavior.

The planned tutorial is a guided walkthrough of the existing application for
farm users and the final-defense demonstration. It will explain the controls
and interpretation of outputs using short, plain-language tooltips. A visible
**Start tutorial** entry should allow replay, with Back, Next, Skip/Close and
progress feedback. A first-use invitation should be dismissible.

| Tutorial segment | What it should explain |
|---|---|
| Welcome and navigation | The workspace sequence, dashboard views and how to leave/replay the tutorial. |
| Orchard and tree inputs | Orchard selection, host stage, tree statuses, source probabilities, zones, and scenario versus saved edits. |
| Weather | Live versus custom weather, forecast dates, scheduled rain breaks, and Cecid soil/light assumptions. |
| Simulation controls | Both pests and engines, duration, repeated runs, outside pressure, protection settings and the Run button. |
| Results and playback | Legends, initial sources versus new infestation, Across runs versus One run, counts and hourly playback. |
| History and exports | Saved results, templates, seeds/version, Excel and final versus displayed-hour reports. |
| Field verification | Inspection records, observation methods, and Present/Absent/Not inspected. |
| Additional tools | Overview, Crop Impact estimates, Surveillance, alerts and Settings where available to the user's role. |

Tutorial behavior requirements:

- Navigation may open the relevant tab/workspace, but tutorial progression
  must not change orchard records or scenario values, run simulations, save
  observations, acknowledge alerts, send emails or initiate exports. Those
  actions require the user's normal controls.
- Before a result exists, explain how to obtain one and allow the user to
  continue or replay the result segment later. Never present sample output as
  a completed forecast for the selected orchard.
- Open conditional panels before targeting them. Wait for the relevant
  control to become available; a missing result, unavailable service or
  role-restricted control must not trap the user in the tour.
- Keep unsaved edits and displayed results intact. End cleanly on logout,
  handle orchard changes without pointing at stale content, and leave normal
  application controls usable after Skip/Close/Finish.
- Use stable target identifiers, readable tooltips, keyboard-accessible
  navigation and appropriate positioning in desktop and narrow layouts.
- Explain weather/source assumptions and estimated outcomes accurately.
  Tutorial completion is user guidance, not evidence of forecast accuracy.

When implementation is requested, check React 18 compatibility and the selected
release's API before adding the dependency. Use the official
[React Joyride getting-started guide](https://react-joyride.com/docs/getting-started),
[props reference](https://react-joyride.com/docs/props) and
[conditional-step guidance](https://react-joyride.com/docs/recipes).
Keep the step definitions and lifecycle handling maintainable rather than
scattering tutorial logic throughout the dashboard.

Acceptance checks should cover first start, Back/Next, Skip/Close/Finish,
replay, conditional targets, no-result and saved-result states, orchard
switching, logout, loading failures, keyboard use and narrow layouts. Confirm
that starting or advancing the tour changes no saved orchard, observation,
alert or account records and triggers no automatic simulation/notification
requests. An optional browser preference may remember dismissal/completion
for that user and tutorial version while retaining manual replay. Then run
the frontend tests and production build and rehearse both pests with both
engines using the manual test plan.

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
npm.cmd install
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

## Farmer email alerts

MangoPoint can send every new, deduplicated risk or biological-gate alert to a
designated list of farmers. Farmers do not need dashboard accounts. Recipient
addresses and provider credentials stay in the backend `.env` file and must never be
placed in `frontend/.env`, SQL files, or committed to Git.

For networks that block SMTP, use Brevo's transactional HTTPS API. Its Free plan
currently supports up to 300 email sends per day. Create a Brevo account, verify
the address used by `SMTP_FROM_EMAIL` as a sender, generate an API key, and configure:

```env
ALERT_EMAIL_PROVIDER=brevo
BREVO_API_KEY=your-brevo-api-key
BREVO_API_TIMEOUT_SECONDS=20

ALERT_EMAIL_ENABLED=true
ALERT_EMAIL_RECIPIENTS=farmer.one@example.com,farmer.two@example.com
ALERT_EMAIL_APP_URL=http://localhost:3000

SMTP_FROM_EMAIL=your-verified-sender@example.com
SMTP_FROM_NAME=MangoPoint Alerts

# Required for forecast alerts while nobody has the dashboard open.
ALERT_MONITORING_ENABLED=true
ALERT_MONITORING_INTERVAL_SECONDS=3600
ALERT_MONITORING_FORECAST_HOURS=48
ALERT_MONITORING_DEDUPE_HOURS=6
```

This path sends `POST https://api.brevo.com/v3/smtp/email` over standard HTTPS
port 443 and does not use `SMTP_USER` or `SMTP_PASSWORD`. See Brevo's official
[transactional email API](https://developers.brevo.com/reference/send-transac-email),
[API-key authentication](https://developers.brevo.com/docs/authentication-schemes),
[sender verification](https://developers.brevo.com/docs/getting-started-with-senders-and-domains), and
[Free-plan limits](https://help.brevo.com/hc/en-us/articles/208580669-FAQs-What-are-the-limits-of-the-Free-plan).

Where SMTP is permitted, set `ALERT_EMAIL_PROVIDER=smtp`. Gmail can then be used
for low-volume installations with `smtp.gmail.com`, port `587`, and
`SMTP_SECURITY=starttls`. Use a Google App Password instead of the normal account
password; Google requires 2-Step Verification for App Passwords. See
[Google's App Password documentation](https://support.google.com/accounts/answer/185833)
and [SMTP settings](https://support.google.com/mail/answer/7104828).

Restart the API after changing `.env`. Then sign in as an administrator and use
`POST /alerts/email/test` in `http://localhost:8000/docs`. Non-secret diagnostics
are available from `GET /alerts/email/status`. Successful alert deliveries are
marked `email_sent=true` and show an **Emailed** badge in the notification list.

Administrators can manage the live recipient list from **Settings > Notification
emails**. The first time that section is opened, addresses from
`ALERT_EMAIL_RECIPIENTS` are imported into the local database. From then on, the
admin-managed list is authoritative, including when every recipient is removed.
Admins can edit contact details, pause or resume delivery, and permanently delete
recipient records from the same settings section. Every signed-in user can also
change their displayed name, login/recovery email, and password from **Settings >
Account**. Changing the recovery email requires the current password.

Password recovery uses the same Brevo or SMTP transport. **Forgot password?**
sends a six-digit code only to the email saved on the user account. The code
expires after 10 minutes, is stored only as a password hash, and locks after five
incorrect attempts. The default `admin@mangopoint.local` bootstrap address cannot
receive mail, so replace it with a real recovery address in Settings before using
password recovery.
Recipient records and their active/paused state are added to the protected cloud
backup outbox. In Supabase, row-level security is enabled and access is revoked
from the `anon` and `authenticated` API roles; the server-side PostgreSQL backup
connection remains the only synchronization path.

The API process must remain running for unattended monitoring. Each scan uses
the orchard centroid, 72 antecedent weather hours, and the configured future
forecast window. Cecid alerts require the orchard's saved stage to be `fruitlet`
and favorable orchard-specific twilight or cloudy-day emergence weather. Synthetic fallback weather is
shown in the weather UI for testing but cannot create an operational Cecid
forecast alert. The alert's **Open Simulation Controls** action selects live
weather and fills the relevant controls; the user must still press **Run
Simulation**. Same-window deduplication prevents repeated alert emails while
allowing a later, distinct favorable window to be reported.

## Supabase cloud backup

Supabase is used as a server-side backup target. Do not put these values in
`frontend/.env` or expose them through Vite:

For a new or existing Supabase project, paste the complete contents of
`supabase/MangoPoint_Supabase_SQL_Editor.sql` into the Supabase SQL Editor and
run it once. This single idempotent file contains the base schema and every
Supabase migration through the latest release.

```env
SUPABASE_DATABASE_URL=postgresql://...
CLOUD_SYNC_ENABLED=true
CLOUD_SYNC_ASSETS=false
CLOUD_SYNC_INTERVAL_SECONDS=7200
```

Codex can use the official project-scoped Supabase MCP connection for database
inspection and migration work. The connection uses Supabase OAuth and keeps
credentials outside the repository. After changing the consolidated schema,
check or apply it directly from the project:

```powershell
.\.venv\Scripts\python.exe -m scripts.sync_supabase_schema --check
.\.venv\Scripts\python.exe -m scripts.sync_supabase_schema --apply
```

The apply command uses an advisory lock and records the consolidated file's
SHA-256 hash in `mangopoint_schema_state`. Running it again without SQL changes
is a no-op. Schema updates run in one transaction; a failed update rolls back
without recording the new hash. Validate SQL against local PostgreSQL before
applying it to Supabase. `AGENTS.md` tells Codex to do this whenever its work
changes the database schema. UI-only changes use the existing data sync and
do not run schema updates.

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
.\.venv\Scripts\python.exe -m scripts.check_recipient_sync
.\.venv\Scripts\python.exe -m scripts.restore_from_supabase --dry-run
.\.venv\Scripts\python.exe -m scripts.restore_from_supabase
```

The restore command must only be run against a replacement or intentionally
empty local database. It restores database rows, including managed alert email
recipients, in dependency order. Orchard
files must be restored separately from your local file backup because they are
not stored in Supabase.

## Simulation Weather Controls

Choose **Live Forecast** or **Custom Weather** for either pest. Custom Weather
starts with one period covering the entire selected simulation duration, so
constant weather does not require repeating daily inputs. Temperature, rainfall,
wind, and cloud cover have preset buttons alongside exact numeric inputs; wind
direction uses compass letters.

Each custom period also has a **Daylight light condition**: Bright sunshine,
Intermittent sunshine, or Dim overcast. Label it as an assumed scenario or an
observed local condition. Cloud percentage alone does not establish dim light.
Live weather combines cloud cover with direct and total solar-radiation estimates;
missing sunlight data remains unknown. Tree-canopy shade alone does not enable
Cecid emergence or movement. The daylight response scales remain provisional.

Use **Add period** or **Edit hours** for changing conditions, then navigate
periods horizontally. **Repeat first day** copies the first 24-hour pattern
through the selected duration. Uncovered hours use the existing default weather
and display a warning; overlapping periods use the later period.

For Cecid Fly, expand **Soil & Cecid test preset** to configure antecedent rain,
select **Moist now** for assumed starting moisture without prior rain, or load
the weather-only dawn/dusk test. The relative moisture strength decreases over
time and receives subsequent rain; it is not a measured soil-water percentage.
The same moisture rule applies to both simulation engines. These controls are hidden for
Fruit Fly. Existing constant-weather, timeline, and hourly-series history records
remain supported. The current biological rules and evidence limits are recorded
in [the fruit pest revision](docs/fruit-pest-model-revision.md).

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

For Cecid wind controls, values remain in m/s. Wind up to 5 km/h has no
controlled-movement activity penalty. Above 5 km/h, a provisional soft
inverse-square curve gradually lowers activity: at 3 m/s (10.8 km/h), the
activity score is about 0.52 rather than a near-zero hard suppression. Wind
direction is separate: provisional downwind assistance begins near 0.9 m/s
and reaches a capped 35% at 15 km/h. The model limits movement to 15 m in
one eligible twilight or cloudy daylight hour. These coefficients are assumptions that
require target-species BPI/field calibration; the compatibility field
`wind_survival_score` contains the same value but does not represent measured
adult mortality.

Both pests support 1, 5, or 9 repeated runs in the simulation controls. Across
runs shows final infestation frequency; One run and playback retain the first
reproducible realization. Additional runs hold per-tree stages and known sources
fixed. History Infected supplies a possible residual source without initially
infesting fruit, while Suspect supplies a possible current infestation. Their
adjustable presence chances default to 50% as scenario assumptions, not field
estimates. Bagging now reduces incoming contributions by 70%. See
[map/source logic](docs/risk-map-and-neighbor-pressure.md) and
[Cecid reliability plan](docs/cecid-reliability-plan.md) for the assumptions and
next validation work.

## Validation

See the [v16 sensitivity and BPI audit](docs/v16-sensitivity-and-bpi-validation.md)
for that version's experimental results and accuracy limitations. The
monthly records support a historical comparison; high category agreement by
itself does not establish tree-level forecast accuracy.

The [v17 model review](docs/v17-model-readiness-review.md) separates initial Fruit
Fly adult pressure from new fruit infestation and clarifies outside Cecid exposure.
Its controlled scenarios were retested; the BPI comparison still needs refreshing.

The [v16 validation defense](docs/v16-validation-defense.md) replayed the
original 20-case design with both v16 engines and preserves the old results
for comparison. Run it with:

```bash
python -m scripts.run_defense_replay --monte-carlo 30 --workers 4
```

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

From the project root, using the configured Python environment:

```powershell
python -m pytest -q
python -m py_compile api\services\simulation_service.py validation\weather_scenarios.py scripts\check_setup.py
cd frontend
npm.cmd test
npm.cmd run build
```

The [testing methods guide](docs/testing-methods-for-defense.md) distinguishes
automated implementation checks, controlled simulations and historical
comparison. The [defense readiness plan](docs/final-defense-readiness-plan.md)
tracks the remaining workflow rehearsal and version-matched evaluation work.
Documentation-only edits need link/content checks; the commands above are for
application changes and do not mean the manual workflow cases have passed.

## Notes

- Runnable helpers live in `scripts/`.
- `run_server.py` is the top-level convenience entry point for starting the API.
- The frontend talks to the API through the Vite dev proxy during local development.
