# Production connection repair and checks - 2026-10-12

The recurring sign-in failure was confirmed before the repair: the live
frontend contained `https://following-functions-merry-lake.trycloudflare.com`,
while the running tunnel advertised
`https://mom-upgrading-capital-wines.trycloudflare.com`. The local API and
database were healthy. Yesterday's successful login check remains archived
in [its original report](remote-access-login-check-2026-10-11.md).

## Published behavior

The frontend now sends remote application requests through `/api` on
`https://mango-point-projects.vercel.app`. The Vercel project-level
**MangoPoint API** rewrite maps `/api/(.*)$` to the current server's `/$1`
path. Its responses have `Cache-Control: no-store`. The service worker also
excludes every `/api` request and root collection URLs such as `/orchards`.
Local companion discovery requires both `healthy` and a connected database.
Network failures have useful connection guidance.

The deployed frontend contains `VITE_API_BASE: "/api"`. The production alias
points at deployment `dpl_Gqhvoq7xVLk8wQbx3aAef9MLcatP`; the Vercel project
root remains `frontend`. The initial path-pattern rule failed live health
verification and was replaced with the verified regex rule before browser
verification. Vercel normalizes the leading regex anchor; the launcher accepts
that normalized source during its unchanged-route check.

Run `start_production.bat` from the project root. It reuses a healthy server,
or starts the API against the configured database. If that database cannot
be reached, it starts the Docker stack and waits for readiness. It starts or
reuses a Quick Tunnel, checks health/CORS, updates only the named API route,
and checks deployed database health and login preflight. Existing unpublished
Vercel routing changes block publication to preserve another operator's edits.
Normal restarts update the route destination without rebuilding the frontend.
An older frontend needs one migration rebuild; `-ForceDeploy` permits a later
explicit frontend rebuild.

## Executed checks

- `npm.cmd test`: 178 passed. The initial sandbox run could not read files
  through esbuild; the final run outside the sandbox passed.
- `npm.cmd run build`: passed. Vite reported the existing large-bundle warning.
- `python -m pytest -q tests/test_remote_access_startup.py`: 6 passed. Checks
  exercise changed/unchanged destinations, API response normalization,
  unrelated staged changes, database/HTML rejection, delayed readiness and
  explicit stale build settings that coexist with an unused `/api` fallback.
- `npm.cmd run test:production`: 1 passed in headless Microsoft Edge. A fresh
  context blocked all loopback companion requests, read healthy/connected
  `/api/health`, submitted the real sign-in form using the existing configured
  account, received HTTP 200 from `/api/auth/login`, saw the dashboard Logout
  control and read authenticated orchard records. Failed remote API requests,
  browser page errors and visible exact `Network Error` messages were all zero.
  Credentials stayed in process memory; traces, screenshots and videos were off.
- `npm.cmd run test:pwa:live`: 1 passed. The deployed frontend reached the local
  companion, retained dismissible connection status behavior, and reloaded
  its cached login shell after internet access was disabled.
- `npm.cmd run test:pwa`: 1 passed against the local production build. The
  cached shell reloaded offline; unavailable-companion guidance remained
  dismissible across another reload.
- `start_production.bat`: final execution exited 0, reused the current API and
  tunnel, reported the published route was already correct, performed no
  frontend rebuild and verified deployed health/database/login access before
  printing the share URL.
- `start_remote_access.bat -CheckOnly`: exited 0 after the final helper changes;
  the explicit deployed build setting was `/api` and no route/deployment update
  was needed.
- PowerShell parsing and `git diff --check`: passed.

## Limits of this evidence

Live startup reused already-running services. A complete laptop cold boot or
forced tunnel restart was not executed. The tests cover route destination
changes and startup readiness independently; this does not establish an uptime
guarantee or control another laptop's browser permissions.

No simulation, orchard edit, observation, alert action, notification or export
was triggered by these browser checks. Both pests/engines are N/A for this
connection-only rehearsal. The unchanged model version is
`2026.10-source-progression-v17`. Biological validation and the remaining
manual workflow cases retain their existing status. No Supabase schema change
was made.

The server laptop, database and tunnel must stay running and online. Cloudflare
Quick Tunnels have temporary hostnames and no uptime guarantee. A permanent
Cloudflare Tunnel hostname or an always-on hosted API/database is needed for
unattended production operation. See the official
[Quick Tunnel documentation](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)
and [Vercel project routing rules](https://vercel.com/docs/routing/project-routing-rules).
