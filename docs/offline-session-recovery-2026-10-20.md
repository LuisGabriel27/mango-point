# Offline session recovery — 2026-10-20

The user reported being logged out after MangoPoint went offline and came back
online. Baseline code inspection found two matching failure paths:

- `AuthContext.jsx` cleared the session on every failed restoration request,
  including unreachable APIs and temporary server failures.
- `apiRuntime.js` chose an API again after each companion health probe. A session
  could move between independent local and remote APIs, whose signing keys and
  persisted session rows are not interchangeable. A resulting 401 ended it.

The original affected-device incident was not replayed or assigned a measured
outage duration. These code paths support the fix without establishing which
path occurred on that laptop.

The frontend now retains the issuing API and last verified user in tab-scoped
session storage. Failed network, timeout and server checks preserve the existing
token and user. A reload can restore this interface while the API is unavailable;
reconnection rechecks the session or retries pending activity renewal. Ordinary
authenticated requests remain on the issuing API even when companion availability
changes. Explicit logout targets that API and clears local session state immediately.

The existing 15-minute inactivity limit, token expiry and absolute session lifetime
still apply. Failed renewals do not extend validity. Authentication rejection
(401), or an inactive-account response from `/auth/me` (403), still ends the
session. Cached user details only support the interface; FastAPI authorizes data
requests. Fresh email-code sign-in still needs a reachable API and working mail.
An older session without a stored API target records its first selected API;
the frontend cannot reconstruct a previously unsaved issuing API.

This is a frontend change. The simulation model, backend, database schema and
cloud-backup service are unchanged. No hosted schema update is required or was
attempted. The unrelated existing `sites/mangopoint-access` worktree changes
were preserved.

Verification uses isolated Edge browser sessions and intercepted API responses.
It sends no actual email, runs no forecast and creates no farm or account records.
The new cases cover local/remote reconnection, preserved unsaved inputs, API
pinning, reloads during network/502/503/504 failures, rejected sessions and explicit
logout during an outage. Existing checks cover inactivity, active renewal,
password-change revocation, late responses, logout confirmation and email-code
sign-in. Offline History checks exercise saved fixture results for Cecid/Fruit Fly
and CA/Tree Graph without running simulations.

Verification on 2026-10-20 passed:

- `npm.cmd test`: 214 frontend checks.
- `npm.cmd run build`: production build; existing large-bundle warning remains.
- 33 distinct isolated Edge browser cases: nine new recovery cases, 14 existing
  email-login cases, six existing session-security cases and four offline History
  cases covering both pests and engines.
- `git diff --check`, changed-document local links and workflow CSV structure.

Browser evidence is retained in `outputs/offline-session-2026-10-20/`:
`results.json` contains the 20 passing existing email/session cases and the initial
recovery fixture failures; `recovery-results.json` contains all nine passing
recovery cases and three History passes; `history-results.json` contains all four
History passes after updating its fixture for ordinary session renewal. This
counts unique passing cases, not repeated executions.

The first browser pass exposed two fixture
issues: the request counter omitted successful renewal, and real clock movement
allowed genuine input to flush to storage between snapshots. The recovery
fixture now counts renewal and uses a paused clock for deterministic deadlines.
The History fixture also originally classified a reconnect-triggered session
renewal as a forbidden farm write. It now handles authentication maintenance
separately while still rejecting farm writes. Initial failure artifacts remain
alongside the final evidence. The first sandboxed unit/browser attempt also
encountered esbuild parent-directory access errors; the checks completed with
approved execution outside that sandbox. No application code was changed to
work around the test environment.

Deployment was pending at initial verification. The API/frontend were subsequently
[released on 2026-10-20](session-recovery-production-release-2026-10-20.md);
a physical disconnect/reconnect rehearsal on the affected laptop remains pending.
Isolated browser passes do not establish deployed-device behavior,
real mail delivery or pest forecast accuracy. See WF-88–WF-91 in the
[workflow plan](manual-workflow-test-plan.md),
[results](manual-workflow-test-results.csv) and
[bug log](manual-workflow-bug-log.csv).
