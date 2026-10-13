# MangoPoint

MangoPoint is a GIS-based pest spread forecasting web application for mango orchards. It combines a FastAPI backend, a React/Vite frontend, cellular automata (CA) and tree-to-tree graph simulation modes, weather-driven biological gates, alerting, decision support, and historical comparison against BPI Guimaras pest monitoring data.

The pest scope is **fruit-attacking Cecid** and **Oriental Fruit Fly
(*Bactrocera dorsalis*)**. The current reviewed model is
`2026.10-source-progression-v17`; its source rules and remaining assumptions are
documented in the [v17 model review](docs/v17-model-readiness-review.md).
The dashboard includes a replayable React Joyride guide for first-time and
returning users.

## Current Capabilities

- Pest spread simulation for fruit-attacking Cecid and Oriental Fruit Fly.
- Grid and tree-graph simulation modes, including real crown-width/crown-radius handling.
- Weather-aware biological triggers using Open-Meteo forecast data, manual weather blocks, synthetic fallback weather, and historical weather CSVs for validation.
- Cecid-specific soil sources, finite short-lived adult cohorts and laying capacity, moisture/light/rain gates, and persistent Weed Habitat relay zones. Local movement has an assumed 15 m hourly limit; outside pressure is a separate directional exposure proxy.
- Fruit Fly initial adult source pressure is retained separately from new fruit infestation. New fruit damage does not create another adult source within the same forecast.
- Explicit source-presence scenarios, bagging/treatment factors, and 1, 5 or 9 repeated realizations with separate frequency and one-run views.
- Multi-orchard API foundation and frontend orchard switching.
- System Overview with a date picker and day/week/month/year filters, orchard summaries,
  field inspection counts, alerts and simulation activity.
- Alerts for high-risk simulation output and orchard-aware scheduled gate monitoring.
- Notification/action workflow for alerts.
- Decision support action plans and treatment/spray scenario controls.
- Field observations and evaluation endpoints.
- Saved simulation History, input templates, and printable reports with recorded model/input assumptions.
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
   for a new run. Print a report, checking its orchard, model
   version and final/displayed reporting hour.
5. **Verify:** Record an actual orchard inspection with the correct tree, pest,
   date and method. Present, Absent and Not inspected are distinct records;
   simulated infestation must not be saved as an observed finding.

Use the [manual workflow test plan](docs/manual-workflow-test-plan.md),
[results sheet](docs/manual-workflow-test-results.csv) and
[bug log](docs/manual-workflow-bug-log.csv) for the full rehearsal. The starting
test sheet contains Not run cases; preparing it does not establish a pass.

### System Overview

The **Overview** tab summarizes records saved to the application database across
all orchards. Its header uses the same compact orchard dropdown, calendar
picker and controls as History. Choose **By day**, **By week**, **By month** or
**By year** to see a Philippine calendar day, Monday–Sunday week, month or year.
The view opens on the current month. **By month** uses a month/year picker;
other views use a date within the desired period. The date defaults to today;
past periods include their full
calendar range, while current periods stop at the time of refresh. Future dates
are unavailable. An independent orchard filter narrows the overview without
changing simulation inputs or the selected orchard in Setup. Day/week/month
bar charts group activity by day; year bar charts group by month. Record types
appear side by side for comparison. **View data table** provides the same counts
in a table. Tables have sortable columns; larger tables add search, a sort dropdown and
10/25/50-row pages. Scroll inside a table to see wide columns or longer pages;
column headers stay visible. Paging and searching do not change summary totals.

Period totals cover completed/failed/other simulation records, inspected field
records, Present/Absent findings, Not inspected records, and alerts raised.
Inspection totals exclude Not inspected and simulation-generated infestation
records. Repeat inspections of the same tree count as separate records; these
totals do not establish orchard prevalence or forecast accuracy. Simulations
use their execution date; field records use their observation date, falling
back to their creation date for older entries without an observation date.

Registered orchards/trees and **Active alerts now** are current snapshots, so
unresolved alerts remain visible even when raised before the selected period.
Browser-only History cache entries are outside this database summary.
The tab refreshes when opened, after saved simulation activity, every minute
while visible, and through **Refresh**. Background refreshes preserve table
search, sorting and pagination. Storage failures show an error with a retry
action; a failed refresh labels any retained records as the last loaded data.
Individual forecast outcomes remain in Results, Crop Impact,
Spread & Weather, and History.

## Guides

The top-bar **Guide** button is always available after sign-in. First-time
users also see a dismissible invitation. Choose the guide that matches the task:

| Guide | Purpose |
|---|---|
| **Quick start** | Learn Setup → Simulate → Results → History → Verify in about three minutes. |
| **Cecid Fly setup** | Check fruitlets, starting sources, soil moisture, rain breaks, outdoor light and wind. |
| **Fruit Fly setup** | Check mature/ripening fruit, days since flowering, initial adult pressure, warmth, daylight and wind. |
| **Understand results** | Read the map, repeated runs, playback, reports, History and field verification correctly. |

Each step highlights the control being explained while a grey overlay reduces
background distraction. The tooltip separates **What to do** from **Why it
matters**, displays the workflow position and provides Back, Next, Skip, Close
and progress feedback. The guides use beginner wording; for example, a pest
“gate” is introduced as a condition that must be suitable.

Guide navigation may show a dashboard tab or open a control panel for the
current explanation. It does not change orchard/scenario inputs, start a
simulation, create a result, save a field observation, acknowledge an alert,
send a notification, change an account or initiate an export. Closing,
skipping or finishing restores the ordinary dashboard view and preserves
unsaved inputs. Missing controls are skipped rather than trapping the user.

The first-use preference is stored in the browser for the signed-in user and
guide version. Browser storage failure does not remove the manual Guide
button. Guide text explains missing/loading/error and no-result states; it
does not manufacture a demonstration forecast or field finding.

The frontend uses `react-joyride` 3.2.0, whose peer range includes React 18.
Automated checks cover the guide definitions and browser lifecycle; the
[manual workflow test plan](docs/manual-workflow-test-plan.md) remains the
record for real browser rehearsal with both pests and both engines.

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

The notification bell loads active alerts for the selected orchard every minute
while the dashboard is visible, when the browser returns to the dashboard, and
when the bell is opened. Its **Refresh** control reloads the list immediately.
Failed refreshes show an error with **Retry** and retain any previously loaded
alerts. These read-only checks do not create alerts or send emails. Repeated
warnings for the same active condition remain deduplicated.

Each alert shows its saved notification date, including the year, and time in
Philippine time (PHT), so older unresolved alerts remain identifiable.

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
