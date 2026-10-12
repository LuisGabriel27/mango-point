# Production startup performance check - 2026-10-12

The user reported that `start_production.bat` stayed on a kilobyte download
display for a long time. The launcher downloaded the deployed approximately
6.5 MB application bundle on every run through Windows PowerShell's
`Invoke-WebRequest`, before displaying the tunnel and route checks.

## Changes

- Large JavaScript bundles now use a text-only .NET HTTP client with automatic
  gzip/deflate decompression, a 30-second request timeout, HTTP failure checks
  and disposal of the client/response. The bundle is inspected as text without
  HTML/link parsing.
- The launcher suppresses PowerShell download progress while retaining clear
  stage messages. It reports the elapsed startup-check time on success.
- Every run still requests live HTML. A checked `/api` configuration is reused
  only when the site and full hashed bundle URL match the saved record. A new
  release, changed site, invalid cache or explicit refresh inspects the bundle
  again. The small cache is ignored and contains no credentials or bundle body.
- Read-only checks never write the cache. A failed live-page request still
  fails even when cached configuration exists. An explicit stale build setting
  cannot be hidden by a bundled `/api` fallback.
- Public API/database readiness, CORS/login preflight, stable Tailscale state
  and Vercel route checks remain. The redundant second deployed health check
  is retained only after a frontend deployment, when a fresh check is needed.

## Executed verification

- The original read-only diagnostic remained at the download stage and was
  stopped after **309.29 seconds**. This was an interrupted run, not a completed
  baseline measurement or proof that every original startup takes that long.
  Only that diagnostic PowerShell process was stopped; API/database services
  were retained.
- An intermediate launcher with progress suppression and configuration caching,
  but still using `Invoke-WebRequest` for the bundle, completed in **174.4
  seconds**. This motivated replacing the large-file reader as well.
- The final `start_production.bat` completed in **9.6 seconds**, reusing the
  checked bundle and existing API/database/Funnel. It confirmed that the
  published route was unchanged, performed no deployment, passed deployed API
  health/database/login preflight and printed the share URL.
- A forced fresh bundle inspection through the final text downloader, executed
  in Windows PowerShell with `-NoProfile`, took **1.4 seconds** and returned
  `/api`. This was read-only and did not change the deployment or cache.
- `.venv\Scripts\python.exe -m pytest tests/test_remote_access_startup.py
  tests/test_offline_companion_startup.py -q --tb=short`: **50 passed**. New
  regression cases check unchanged-release reuse, release/site changes, explicit
  refresh, missing/corrupt cache in read-only mode, progress suppression and
  failure of the live HTML request.
- `npm.cmd run test:production`: **1 passed** in headless Microsoft Edge with
  loopback requests blocked. Remote health reported a connected database;
  login and authenticated orchard GET returned **200**, Logout appeared, and
  failed API requests/page errors were zero. Credentials stayed in process
  memory; screenshots, videos and traces were disabled.
- PowerShell parsing, local documentation links, CSV column counts and
  `git diff --check` passed.

## Limits

These timings apply to the already prepared server laptop and its current
network. Docker cold image preparation, a laptop reboot and a new Funnel's
initial activation were not performed. Starting absent services and provider
availability can still take longer. The change does not bypass readiness or
promise a fixed startup time during an outage.

No simulation, record edit, notification or export was submitted. Both pests
and engines are N/A for this connection check. The model remains
`2026.10-source-progression-v17`; no Supabase schema change was made. Earlier
connection and stable-access reports are preserved.

References:

- [PowerShell progress preference](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_preference_variables?view=powershell-5.1)
- [.NET HTTP client timeout](https://learn.microsoft.com/en-us/dotnet/api/system.net.http.httpclient.timeout?view=netframework-4.8.1)
