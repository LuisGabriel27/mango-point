# MangoPoint organization request website

Implementation and verification: 12–13 October 2026 (Asia/Manila).

## Visitor and administrator workflow

The separate website introduces MangoPoint and accepts inquiries from government
offices, cooperatives, farms, research/education organizations, businesses and
other sectors. The form collects organization, sector, location, contact name,
email, requested arrangement and a description of the intended use. Phone and
orchard count are optional. Contact consent is required and recorded as
`access-inquiry-v1`.

Successful submission returns a reference and receipt time. A failed submission
keeps the entered details; identical retries reuse the same submission ID.
Editing the details creates a new submission identity. Form details are not
persisted to browser storage. A receipt is shown only after the backend confirms
the saved request. There are no demonstration requests in the production inbox.

The private inbox uses the existing MangoPoint administrator login. Analysts and
operators cannot read or update requests. An administrator can search by
organization, contact, email or reference, filter by review status, page through
records and save private notes. Closing the dialog preserves unsaved notes in
memory until logout or page reload. A conflicting review returns HTTP 409 and
requires loading the latest saved review before retrying. Loading that review
is an explicit action that replaces the current edits.

The statuses are New, In discussion, Approved and Closed. Approval records a
review decision. It does not provision an account or create subscription
entitlements. Payments, contracts, email notifications and automated customer
onboarding are outside this implementation. Customer sign-in links to the
existing MangoPoint application.

## Application boundary and storage

| Endpoint | Access | Effect |
| --- | --- | --- |
| `POST /access-requests` | Public | Save an inquiry or return its existing receipt for an identical retry. |
| `GET /access-requests` | Persisted administrator | Search/filter/page the private inbox and read status counts. |
| `GET /access-requests/{request_id}` | Persisted administrator | Read the latest request and review. |
| `PATCH /access-requests/{request_id}` | Persisted administrator | Save status and notes with a checked version and reviewer identity. |

The FastAPI service stores records in `access_request`. Its transactional trigger
queues changes in the existing `sync_outbox`; the cloud-sync service handles
backup without a second browser-facing database connection. Restore ordering
includes requests after user accounts. Applicant records have no public
Supabase RLS policy, and `anon` / `authenticated` receive no direct table grants.

The public endpoint accepts a bounded allowlist of fields. It rejects missing
consent, invalid enums/emails, extra properties and a filled honeypot. A durable
per-client hourly quota defaults to five new requests. The client address is
stored as an HMAC, rather than a raw address; retries of accepted requests do
not spend the quota. PostgreSQL advisory locks serialize request IDs and
same-client submissions across workers. Configure trusted proxy forwarding in
the API deployment so client addresses are determined by the trusted server,
not by accepting arbitrary forwarded headers in application code.

The reviewer token is kept in browser memory and, when available, session
storage under a website-specific key. Storage failure permits a memory-only
session. Logout clears cached requests, notes and token state and aborts pending
requests. Applicant-provided content is rendered as text.

## Setup and local preview

The website is static HTML/CSS/JavaScript with the existing MangoPoint brand
assets. It introduces modeled scenarios without claiming measured accuracy,
validated crop benefits or current v17 BPI agreement. The illustrated orchard is
explicitly labeled and is not a simulation result.

Add the precise deployed origin to the server-side `.env`:

```dotenv
ACCESS_WEBSITE_ORIGINS=["https://mangopoint-access.almondbear10.chatgpt.site"]
ACCESS_REQUEST_LIMIT_PER_HOUR=5
```

Preserve existing `CORS_ORIGINS`. Restart the API after editing origins.
For local browser testing, also allow `http://127.0.0.1:8088` as an access
website origin. Browser code contains only the public API base
`https://mango-point-projects.vercel.app/api`; no database credentials or service
keys are shipped to the website. The source manifest belongs to its separately
registered Site and must retain that exact project ID.

From the main project directory, validate SQL locally before applying it to
the hosted project:

```powershell
.venv\Scripts\python.exe -m scripts.check_access_request_schema
```

This applies the inquiry migration and checks its table and sync trigger in a
transaction that is rolled back. The local migration, hosted migration and
consolidated SQL Editor file carry the same change:

- `db/migrations/0012_organization_access_requests.sql`
- `supabase/migrations/202610120001_organization_access_requests.sql`
- `supabase/MangoPoint_Supabase_SQL_Editor.sql`

Use the official project-scoped Supabase connection for hosted schema changes,
then run the required synchronization command:

```powershell
.venv\Scripts\python.exe -m scripts.sync_supabase_schema --apply
```

The prescribed schema synchronization command completed with **Supabase schema
updated** after local validation and explicit approval to use that command.
The existing project-scoped MCP connection was found in local Codex
configuration, but its login refresh failed at OAuth token exchange; no MCP
schema query or migration was claimed as successful. The approved project
command performed the hosted update. API startup applied the local migration,
and local requests continue to use the existing cloud-sync queue for backup.

Build and preview the website:

```powershell
cd sites/mangopoint-access
node build.mjs
node server.mjs
```

Open `http://127.0.0.1:8088/` or `http://127.0.0.1:8088/review.html`.

## Executed verification

- Local PostgreSQL inquiry migration and backup trigger validated in a
  transaction with rollback.
- Full Python suite: **882 passed**, with one existing Starlette/httpx
  deprecation warning, using `.venv\Scripts\python.exe -m pytest -q`.
- Website unit checks: **3 passed**, covering retry identity, response failures
  and authorization-header handling.
- Existing application frontend: **178 tests passed**, and `npm.cmd run build`
  succeeded. Its existing large-bundle warning remains. Sandbox access failures
  were resolved by running these checks outside the sandbox.
- Actual Edge browser automation on the local static website passed required
  form validation, failed-submission preservation, safe retries, receipt focus,
  360 px public layout, role restrictions, empty inbox, private note drafts,
  review conflicts and recovery, safe rendering of applicant text, keyboard
  focus, 390 px review layout and logout during a pending load.
- Browser checks intercept API calls with isolated test fixtures. They do not
  create production requests, observations, simulations, accounts, alerts,
  notifications or licensing records. They establish UI behavior, not
  production service availability or model/field accuracy.

Run the website checks from its directory:

```powershell
node --test tests/submission.test.mjs
```

With the local static preview running, use the main project directory:

```powershell
node scripts/check_access_website.cjs
```

Browser automation uses the existing frontend Playwright installation and
installed Microsoft Edge. Screenshots are saved in the ignored
`outputs/access-website/` directory. No frontend dependency was added. The
existing MangoPoint manual workflow sheets are unchanged; these checks do not
establish new passes for either pest or engine.
