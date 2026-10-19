# Automatic offline History preparation

The dashboard now prepares saved completed simulation results in the background
after sign-in. Managers no longer need to open each result while online before
viewing it offline. Preparation runs while History is hidden, pages through all
saved runs, and ignores the displayed orchard/month/page filters.

Only missing complete result payloads are downloaded, one at a time, through
the existing authenticated FastAPI endpoints. Pages and detail requests stay on
the API that supplied the list. Saved maps, time series, weather, request inputs
and metadata are retained. This change adds no simulations, farm-record writes,
cloud-backup requests, backend/model changes or hosted schema changes.

History shows a preparation count across all orchards, per-result **Available
offline** / **Online only** labels and incomplete-download guidance. Reconnection
or **Refresh** retries missing downloads. Deletion/Undo reconcile browser copies;
missing/deleted server results cannot fall back to obsolete output. Logout,
session invalidation, refresh and component cleanup cancel pending preparation.

IndexedDB remains the primary browser store. When its writes fail but reads
still work, localStorage-only results are included in History and detail loads.
The fallback keeps at most 25 non-deleted entries, subject to available space;
deletion markers are retained. Readiness is recalculated from durable storage,
including any fallback evictions, and storage failures remain visible.

Offline viewing uses the existing signed-in session. Fresh sign-in and dashboard
session restoration still require the API; this change does not bypass session
expiry. Uncached results and server-generated Excel exports need the API.
Browser data can be cleared or evicted, so preparation is not a durable backup.

## Verification on 2026-10-19

`npm.cmd test` passed all 210 frontend checks. New checks cover all pests/engines,
all orchard/date scopes, pagination beyond 1,000 results, original evidence,
skipping complete cached runs, interruption/retry, deleted/missing runs,
cancellation, authorization failures, unavailable/denied/full storage and failed
simulation records. `npm.cmd run build` passed with Vite's large-chunk warning.

Browser evidence uses isolated Microsoft Edge sessions and mocked API responses;
it creates no actual orchard, simulation, inspection or account record. The
checks cover unopened results cached before visiting History; loading both
pests and engines from saved browser data with browser networking offline;
orchard selection; preserved maps/playback/seed/model metadata; narrow History
layout; interrupted preparation/reconnection; session-end cancellation; and
readable IndexedDB with failed writes and usable fallback results. All 19 browser
checks passed, including existing History deletion/Undo and forecast-verification
regressions, using this command:

```powershell
cd frontend
npx.cmd playwright test tests/history-offline-cache.spec.js tests/history-deletion.spec.js tests/forecast-verification.spec.js --output ../outputs/history-offline-cache-2026-10-19/verified --reporter list
```

The fixture output is stored in ignored
`outputs/history-offline-cache-2026-10-19/verified/`, including the narrow offline
History screenshot. Executed cases are identified in the
[workflow results](manual-workflow-test-results.csv); the
[bug log](manual-workflow-bug-log.csv) records the user-reported cache limitation.
These are implementation checks, not simulation experiments, BPI comparisons or
prospective field validation. Real deployed-device preparation, actual browser
quota exhaustion and full offline report/Excel export rehearsal remain separate
checks; the browser fixtures do not establish those outcomes.

The changes are local and have not been published by this work. No Supabase
schema update is required or applied.
