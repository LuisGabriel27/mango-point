# Offline companion connection check - 2026-10-12

The reported issue is on a groupmate's laptop: offline simulation says that
MangoPoint cannot be reached, although local `/health` reports healthy with a
connected database. Allowing browser local network access did not make the
Local-first banner appear. Their attempted CORS diagnostic contained Facebook
formatted/tracking links and failed; it does not establish a missing CORS
header. A corrected follow-up command returned a blank `Allowed origin:`.
This confirms that their local health response does not allow the deployed
Vercel origin. The API is reachable; cross-origin browser access is blocked.
Whether their `.env` lacks the origin or their existing container retains an
older environment has not been inspected. A repair on that laptop remains
pending execution.

## Changes

- `start_offline_companion.bat` now delegates to a PowerShell launcher. Normal
  startup uses prepared Docker images with `--no-build --pull never`, waits
  for container health and then confirms API/database readiness. `-Prepare`
  permits an online build when services are absent; an already healthy API is
  reused. Deliberate image updates are documented separately.
- Readiness also checks the exact deployed Vercel origin on both health GET
  and login OPTIONS. A rejected origin stops startup with instructions to
  update the existing local environment and recreate the API container.
- `-CheckOnly` checks an existing local API without starting Docker, editing
  configuration or changing production routing.
- `-RepairCors` adds the exact Vercel origin to the affected Docker project's
  existing `.env`, retaining other origins/settings and saving a private
  backup under ignored `outputs/offline-companion/`. It recreates only the
  running API container without rebuilding/downloading images or restarting
  the database, then repeats health and CORS checks. Malformed/duplicate
  settings stop before any write. Repeating repair against a working API
  does not change the environment or containers.
- The Docker API healthcheck requires JSON `status: healthy` and
  `database: connected`, rather than only a successful HTTP response.
- The [troubleshooting guide](offline-companion-troubleshooting.md) covers
  CORS, browser permission, local accounts, cache preparation and testing
  without blocking loopback. The shareable helper ZIP contains only the
  launcher, three supporting scripts and that guide.

## Executed verification

- `start_offline_companion.bat -CheckOnly`: **exit 0** against the already
  running native API on this laptop. Database readiness, Vercel health CORS
  and login preflight passed. Docker Desktop was not running and was not
  started by this check.
- `.venv\Scripts\python.exe -m pytest tests/test_offline_companion_startup.py
  tests/test_remote_access_startup.py -q`: **43 passed**. Includes offline
  image flags, preparation flags, connected-database health responses, CORS
  rejection, readiness failures and read-only behavior using mocks. Repair
  checks cover retaining origins, settings, UTF-8 text and CRLF lines; private
  backup integrity; repeated runs; malformed settings; refusing a missing
  Docker API; API-only recreation and access checks afterward.
- `docker compose config --quiet`: **passed**. Configuration was validated
  without printing the expanded environment.
- Frontend `npm.cmd test`: **178 passed**; `npm.cmd run build`: **passed**.
  The build retained its existing large-chunk warning. No new dependency was
  installed and the deployed application code was not changed for this fix.
- Frontend `npm.cmd run test:offline-api`: **1 passed**, headless Microsoft
  Edge, using the deployed Vercel frontend and this laptop's existing API.
  The test granted local network permission, cached the app online and then
  blocked browser HTTP(S) requests except loopback port 8000. Cached-page
  reload succeeded and a remote `/api/health` request failed as expected.
  Local login returned **200**, Logout appeared, and authenticated local
  orchard GET returned **200**.
- A local POST to `/simulation/run-simulation` with empty inputs returned
  structured **422** validation. This checks local network/authentication/CORS
  before model execution; it is not a completed simulation or model validation.
  No forecast was submitted, application records edited, notification sent or
  export initiated. Credentials remained in process/browser memory; traces,
  screenshots and videos were disabled.
- PowerShell parsing and `git diff --check` passed.

## Limits

Docker cold startup and a physical Wi-Fi disconnect were not executed here:
the already running local server was preserved. Startup branching was tested
with mocks; the browser test blocked internet traffic while allowing loopback.
It does not prove that the groupmate's browser has permission or that their
existing session uses their local account. Their blank CORS header was reported
by the user; no repaired-container/browser retest has been executed on their
laptop. The live local API here already allowed Vercel, so mutation/recreation
was tested on temporary fixtures with Docker mocks.
Full offline forecasts for both pests and engines remain unexecuted in this
connection rehearsal. Those cases are N/A, rather than recorded as Pass.

The model remains `2026.10-source-progression-v17`. No Supabase schema change
was made. Existing production/stable access evidence is preserved.
