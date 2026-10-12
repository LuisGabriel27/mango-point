# Stable laptop access check - 2026-10-12

MangoPoint's server laptop now uses **https://msi.tail814675.ts.net** through
Tailscale Funnel. Visitors keep opening
**https://mango-point-projects.vercel.app**. The published Vercel **MangoPoint
API** route maps `/api/(.*)$` to `https://msi.tail814675.ts.net/$1`, with
`Cache-Control: no-store`. The frontend remains configured to use `/api`.
No frontend rebuild was needed for this switch.

## Activated configuration

- Installed the official Tailscale 1.104.1 Windows package using winget;
  the installer hash verification passed. The Windows service is running
  with Automatic startup.
- The user signed in/registering this laptop and disabled its device key
  expiry. The initial status showed expiration on 2027-04-10; the final
  running/online device status contains no key expiry.
- The user completed Tailscale's Funnel activation page. The launcher
  configured `funnel --bg --https=443 http://127.0.0.1:8000`.
- Live Funnel JSON contains a top-level HTTPS port 443 handler, a root proxy
  to `http://127.0.0.1:8000`, and `AllowFunnel` enabled for the stable hostname.
  This is the persistent configuration, without a foreground session.
- `tailscale set --unattended=true` completed. A read-only preferences check
  confirmed `ForceDaemon: true`; other preferences/account information were
  not printed or saved.
- Setup saved the provider, public API origin and configuration version in
  `outputs/remote-access/connection.json` only after deployed API health and
  login preflight passed. `git check-ignore` confirmed the file is ignored.
  It contains no credentials. Future `start_production.bat` runs read it.

The launcher rejects device key expiry, missing sign-in, a changed saved DNS
name and conflicting Serve/Funnel configuration. It stops on invalid saved
settings rather than falling back to a Quick Tunnel. Explicit setup can
register a deliberately changed hostname. Read-only checks cannot start the
server, configure unattended mode, save settings or redeploy the frontend.

## Executed checks

- `.venv\Scripts\python.exe -m pytest tests/test_remote_access_startup.py -q`:
  **21 passed**. Coverage includes stable provider selection, rejecting
  temporary/credential-bearing origins, online/device expiry checks,
  persistent mapping creation, unchanged/read-only behavior, changed names,
  preserving other services, and the existing route/readiness checks.
- The first setup stopped on the expiring device key before changing Vercel.
  After the user disabled expiry and enabled Funnel, setup published the
  stable route. Its initial 90-second deployed readiness wait expired while
  the connection was becoming available; it did not save the configuration
  or print the share-ready message. An early browser check also failed at
  API health because the upstream response was not JSON. The exact initial
  upstream failure was not captured; this is not proof of a specific DNS or
  certificate failure.
- Stable setup now allows a ten-minute readiness wait for first activation,
  matching Tailscale's documented public DNS propagation window. Re-running
  `setup_stable_access.bat` exited **0**, reused the published stable route,
  saved the connection and verified deployed health/database/login access.
- Direct stable API health and login OPTIONS returned **HTTP 200**, with
  `database: connected` and the correct Vercel origin allowed.
- A public DNS-over-HTTPS lookup returned two public IPv4 answers for the
  stable hostname. This check bypassed the laptop's private MagicDNS lookup.
- A Vercel API read confirmed the sole enabled **MangoPoint API** rule targets
  `https://msi.tail814675.ts.net/$1` and has no staged change.
- `start_production.bat` exited **0**, reused the saved Tailscale address,
  reported the published route was already correct, performed no deployment,
  and printed the share URL after deployed API/database/login readiness.
- `start_remote_access.bat -CheckOnly` exited **0** using the saved stable
  connection and verified deployed health/login access without writes.
- `npm.cmd run test:production`, executed after setup readiness: **1 passed**
  in headless Microsoft Edge. Loopback companion requests were blocked. The
  existing account signed in through `/api/auth/login` with **HTTP 200**, the
  dashboard Logout control appeared, and authenticated `/api/orchards`
  returned **HTTP 200**. Failed API requests, browser page errors and visible
  exact `Network Error` messages were zero. Credentials remained in process
  memory; traces, screenshots and videos were disabled.
- PowerShell parser checks and README local-link checks passed. Combining
  `-CheckOnly` with `-RememberConnection` correctly stopped before startup or
  production writes. Both manual CSV files passed column-count validation;
  `git diff --check` passed. The initial failed browser check and successful
  retest are recorded separately in the workflow results under NET-003.

## Limits and operation

Use `start_production.bat` after starting/restarting the laptop and wait for
the share-ready message. Keep the laptop awake, online, with the API and
database running. Keep its Tailscale account/device and device/tailnet names.
The URL is stable across ordinary service restarts; changing the registered
device/name/account can require deliberate reconfiguration.

A Windows cold reboot, Windows logout, forced API restart and forced
Tailscale service restart were not executed. The live checks establish saved
configuration and successful production access, not an uptime guarantee.
Funnel is currently beta and has non-configurable bandwidth limits.

This rehearsal did not submit a simulation, edit orchards/observations/alerts,
send notifications or export records. Both pests and engines are N/A for this
connection-only check; biological/manual workflow statuses are unchanged.
The model remains `2026.10-source-progression-v17`. No Supabase schema change
was made. The earlier
[connection repair report](production-connection-check-2026-10-12.md) and
[2026-10-11 login evidence](remote-access-login-check-2026-10-11.md) are preserved.

Official references:

- [Tailscale Funnel and DNS propagation](https://tailscale.com/docs/features/tailscale-funnel)
- [Persistent Funnel background mode](https://tailscale.com/docs/reference/tailscale-cli/funnel)
- [Device key expiry](https://tailscale.com/docs/features/access-control/key-expiry)
- [Windows unattended mode](https://tailscale.com/docs/how-to/run-unattended)
