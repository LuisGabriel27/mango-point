# Fixing offline connection errors on another laptop

Use this guide when the Vercel app reports that it cannot reach MangoPoint
during an offline simulation, including when
`http://127.0.0.1:8000/health` is already healthy with a connected database.

Each offline laptop needs its own local API/database, browser permission,
local account and cached app. Docker readiness on one laptop does not prepare
another laptop's browser. Run the checks below on the affected laptop.

## Check API access from the deployed site

Use the current companion launcher and its three supporting scripts from this
project, then run:

```powershell
.\start_offline_companion.bat -CheckOnly
```

If sharing the helper ZIP, extract it into the affected laptop's project folder
so `start_offline_companion.bat` sits beside `docker-compose.yml` and its scripts
are inside `scripts/`. The helper package contains no `.env` or database data.

The command reads local API/database health and checks CORS for health and
the authenticated login preflight. It does not start containers, rebuild,
change production, modify `.env` or send credentials. Its success describes
server-side access; browser permissions and its cached app still need the
checks below.

If the check reports a blocked deployed origin, edit this laptop's existing
`.env` and add `https://mango-point-projects.vercel.app` to `CORS_ORIGINS`,
keeping the origins that are already needed. For the project's standard
development origins, the complete value is:

```dotenv
CORS_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000","http://localhost:5173","http://127.0.0.1:5173","https://mango-point-projects.vercel.app"]
```

For this project's already running Docker API, the current launcher can apply
this repair automatically:

```powershell
.\start_offline_companion.bat -RepairCors
```

It adds only the deployed origin, keeps existing origins and other `.env`
settings, saves a private backup under ignored `outputs/offline-companion/`,
recreates only the API container using its existing image, and checks health
and CORS again. The database container/volume is retained. Keep the backup
private because it contains this laptop's original credentials. No build or
image download is needed. An already accessible API is reused without changes.
`-RepairCors`, `-Prepare` and `-CheckOnly` are separate operations.

Apply the changed environment to an existing Docker API image:

```powershell
docker compose up -d --no-build --pull never --force-recreate --wait --wait-timeout 120 api
.\start_offline_companion.bat -CheckOnly
```

An environment edit requires container recreation; `docker compose restart`
alone does not apply it. The mounted database data is retained. If the API is
running directly in Python, restart that process after the `.env` edit instead.
Keep passwords, auth secrets and cloud credentials private.

For a laptop without the new launcher yet, this checks the health response's
allowed origin directly:

```powershell
$r = Invoke-WebRequest -UseBasicParsing -Uri ('http://' + '127.0.0.1:8000/health') -Headers @{ Origin = ('https://' + 'mango-point-projects.vercel.app') }; Write-Output ('Allowed origin: ' + $r.Headers['Access-Control-Allow-Origin'])
```

The value should be `https://mango-point-projects.vercel.app`. A blank value
means the response does not allow that browser origin. Directly opening
`/health` is a navigation and does not establish cross-origin browser access.
Copy the complete code line as plain text. Facebook/Messenger can replace URLs
with formatted links; pasted `[address](tracking-link)` text is not a valid
PowerShell URL. A command error is not a CORS result.

## Prepare the browser connection while online

1. Open **https://mango-point-projects.vercel.app** in a current Chrome/Edge
   browser on this laptop. Use the same browser profile for later offline use.
2. Open the site's permissions/settings beside the address bar and allow
   **Local network access** or the local-device/loopback permission shown by
   the browser. Allow the prompt if it appears. Browser access to loopback is
   gated separately from whether a container is healthy.
3. Return to MangoPoint and reload while online. If it still runs an older
   page, save any needed work and use **Ctrl+Shift+R** while online, then reload
   normally once. Avoid clearing site data: that can remove local History.
4. Confirm **Local-first mode** appears. A previously dismissed status message
   can stay hidden in that tab; opening a new tab in the same profile allows a
   fresh check. In developer tools, requests should target
   `http://127.0.0.1:8000`, including login and `/simulation/run-simulation`.
5. While online, sign in using an account in this laptop's local database and
   verify the code sent to its saved email. The local API also needs working
   Brevo/SMTP delivery. If a session was
   created against another server, sign out and sign in again through the
   now-working local connection. An account existing only on the remote server
   may not exist in this local database.
6. Reload once and allow the PWA to finish caching while online. Install the
   app if desired. The app shell must be cached in this profile before a
   disconnected launch.

Browser local network permission is separate from CORS. If the diagnostic
passes and Local-first mode remains absent, check the exact site URL/browser
version and its network errors. A managed browser can restrict this permission;
use the organization's allowed browser configuration.

## Start and rehearse offline

```powershell
.\start_offline_companion.bat
```

Normal startup uses existing images with `--no-build --pull never` and waits
for API/database health. If images are missing or need a code update, prepare
while online with `start_offline_companion.bat -Prepare` when services are absent,
or deliberately rebuild while online:

```powershell
docker compose up -d --build --wait --wait-timeout 120
```

After browser preparation, disconnect Wi-Fi, keep Docker/API/database running,
keep the existing verified browser session, select **Custom Weather** and run
the normal forecast. A fresh login cannot complete without email delivery.
After logout, a 15-minute inactivity expiry or the absolute session deadline,
reconnect before signing in again. An offline PWA cache is not an authenticated
session and cannot bypass email verification.
Live weather, online map tiles and notification delivery require internet.
Use the companion launcher on each offline laptop; the production launcher
belongs to the designated shared server operator.

If rehearsing with developer tools, note that the browser's **Offline** network
emulation can block localhost requests in the tested tab as well. A healthy
API in another tab or PowerShell does not make an emulated-offline request in
that tab succeed. A physical Wi-Fi disconnect, or network blocking that permits
loopback, checks the intended local companion behavior.

For ongoing failures, provide the read-only launcher's output, browser/version,
actual app URL and the failed local request's error/status. Exclude passwords,
Authorization headers, tokens and private `.env` values.

Official references:

- [Chrome Local Network Access](https://developer.chrome.com/blog/local-network-access)
- [Docker Compose startup/health waiting and offline image flags](https://docs.docker.com/reference/cli/docker/compose/up/)
- [Docker Compose startup order](https://docs.docker.com/compose/how-tos/startup-order/)
- [Docker Compose restart and unchanged environment](https://docs.docker.com/reference/cli/docker/compose/restart/)
