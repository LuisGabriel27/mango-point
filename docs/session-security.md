# Session security

New sign-ins require the account password and a six-digit code sent to the
account's existing email through the configured Brevo/SMTP transport.
`POST /auth/login` checks the password and returns a pending challenge, a masked
email address, expiry and resend delay. It returns no access token, user profile
or session slot. `POST /auth/login/verify` creates the session only after the
code is accepted; `POST /auth/login/resend` replaces a pending code. The browser
keeps pending details in memory, clears the password after the first step and
pins verification/resend to the issuing API. Leaving the login screen cancels
pending browser authentication; late responses cannot restore it. Reloading
starts a fresh sign-in rather than restoring a partial session.

Login codes expire after **5 minutes**, allow **5 incorrect attempts**, and
have a **60-second resend cooldown**. These limits are configurable through
`LOGIN_CODE_EXPIRE_MINUTES`, `LOGIN_CODE_MAX_ATTEMPTS` and
`LOGIN_CODE_RESEND_SECONDS`. Codes are stored as password hashes in the existing
`password_reset_challenge` table with purpose `login`, the account email and
credential stamp. No schema change is needed beyond the existing account-security
migration. Login challenges remain excluded from cloud backup. A reset/change
code cannot be exchanged for a login session, and a login code cannot reset a
password. Each purpose has its own resend cooldown.

Account and challenge row locks prevent concurrent code reuse and lost attempt
counters. An inactive account, changed password/email, expired, consumed or
replaced challenge is rejected. The two-session limit is checked when requesting
the code and again during verification. A valid code is consumed even if the
available session slot fills before confirmation. Failed email delivery rolls
back the new challenge and never grants a session; a failed resend preserves
the earlier still-valid code. Codes are omitted from sign-in email subjects and
application logs. They appear only in the private email bodies.

**Fresh sign-in requires internet and a working account inbox**, including on
an offline companion. There is no password-only fallback when email fails.
An existing unexpired session can keep using its authoritative local API and
database without internet, subject to the ordinary idle and absolute limits.
After logout or session expiry, reconnect to receive a new sign-in code. Existing
independent companion accounts need their own reachable email and mail transport.
Do not advertise completely offline cold-start login with this email-code policy.

Each account can have at most two active sessions against the same authoritative
API database. Login locks the account row before counting and allocating slots,
so simultaneous requests across API workers cannot allocate a third session.
A third login returns HTTP 409 with instructions to log out elsewhere or wait
for an idle session to expire. Each separate login counts, including a new login
in another tab; tabs already sharing a token use one session. Independent offline
companion databases do not share a global session count.

MangoPoint ends a session after 15 minutes without user interaction. Real
pointer input, keyboard input, wheel scrolling and touch renew it. Automatic
weather refreshes, alerts, map playback, tutorial scrolling and API reads do not.
The last interaction time survives a page reload in session storage. A suspended
tab checks the elapsed time before accepting new input when it resumes.

The API issues access tokens valid for at most 15 minutes. The frontend sends
`POST /auth/session/refresh` after recent user input, with renewal requests
throttled to 30 seconds. The token expiry accounts for the age of that input.
Background `GET /auth/me` checks validate credentials without extending expiry.
An expired token cannot be renewed. Renewals also preserve the original absolute
session lifetime configured by `AUTH_ACCESS_TOKEN_EXPIRE_MINUTES` (8 hours by
default). A failed network renewal never extends a token's validity.
Renewal updates the existing database session rather than allocating a slot.
Ordinary Logout revokes that session on the server and immediately releases its
slot. Replaying an old token cannot restore a logged-out session. Closing the
browser without logging out releases its slot when its idle expiry passes.

Settings password fields have independent Show/Hide buttons. Changing a password
requires the current password and a six-digit code sent through the configured
Brevo/SMTP transport to the account's existing email. Recovery email changes
also require a code sent to the existing inbox, preventing a password-only
change of where password verification codes go. No credentials change while
requesting a code. A failed delivery rolls back the challenge and leaves the
account and current sessions unchanged.

Only a code hash is stored. Codes expire after 10 minutes by default, allow five
incorrect attempts and have a 60-second resend cooldown per account. Resending
invalidates older codes for that purpose. Challenges are bound to an account,
its current email and credential stamp, and a purpose (reset, password change,
or recovery email change). A code cannot be reused, submitted by another
account, or exchanged between these flows. Changing the email or password
invalidates outstanding codes tied to the previous account details. Email
verification protects account changes separately from the sign-in email code.

Each token contains a keyed HMAC derived from the account ID and stored password
hash. The raw password and password hash are never included in a token. The API
compares this stamp against the current account on every authenticated request.
Changing or resetting the password changes the stored hash, immediately making
all old tokens invalid across devices and API workers. Profile/name/email changes
do not invalidate this stamp. A wrong current password changes no credentials.
Authentication requires the authoritative PostgreSQL database and, for a new
login code, working email delivery. The former
database-unavailable default-admin fallback is disabled because it could bypass
persisted session slots and account changes. Internet-offline operation remains
available to an existing verified session when the local companion API and local
PostgreSQL are running.

After a successful password change, the current browser clears its session and
shows Login with instructions to use the new password. Other connected devices
sign out on their next authenticated request or session check, normally within
30 seconds while visible. Hidden tabs check when they resume. A response from a
previous session cannot restore authentication after logout or replace a newer
login. Session maintenance creates no orchard, forecast or field records.

Deploy both the frontend and backend, then restart the API. API startup applies
`db/migrations/0012_account_session_security.sql` locally: it creates
`auth_session` and adds verification-purpose/account binding columns to
`password_reset_challenge`. The matching hosted migration is
`supabase/migrations/202610170000_account_session_security.sql`; the consolidated
Supabase SQL Editor file includes the same changes. Validate locally, use the
official project-scoped Supabase MCP connection, then run
`python -m scripts.sync_supabase_schema --apply` as required by `AGENTS.md`.
Hosted session access is protected by RLS with no grants to browser API roles.
Session slots and verification codes are ephemeral and excluded from cloud
backup. Legacy tokens without a persisted session ID require a fresh sign-in.

For the email-login release, first confirm that every active account has a
reachable inbox and that its authoritative API has working mail configuration.
Update the backend and frontend as one release: the new frontend rejects a
password-only API response, and an old frontend does not understand the new
pending challenge response. This change does not alter already-issued valid
sessions or their existing expiry rules. No production account emails are
automatically replaced, and no real email delivery is established by mocked
automated tests. See the [email-login implementation check](email-login-security-2026-10-19.md).

The configured mail provider must be able to deliver to the account inbox.
Set a real `DEFAULT_ADMIN_EMAIL` before initially seeding an account. An existing
account whose address is a placeholder or whose inbox is lost needs controlled
server-side administrator recovery; changing the bootstrap `.env` address does
not silently replace a saved recovery email. This release does not add an
unauthenticated recovery-email bypass.

Automated checks use isolated PostgreSQL schemas, mocked database sessions and
intercepted browser API responses. They verify concurrent two-slot allocation,
logout revocation, timeout/renewal, preserved inactivity across reloads and
suspended tabs, purpose/account/email-bound codes, expiry, failed-attempt
lockout, delivery failure, password change/reset revocation and late-response
protection. Browser checks cover independent password toggles, email confirmation,
recipient validation and deletion cancellation/retry on desktop and mobile.
These checks do not send real email, change production passwords or establish
pest prediction accuracy. Real deployment rehearsal remains in
WF-74 through WF-77 of the [manual test plan](manual-workflow-test-plan.md).

Historical verification on 2026-10-13 passed 877 Python tests, 194 frontend tests, four
session browser checks, 16 Verify/tutorial browser regression checks and the
production frontend build. Local execution logs are in
`outputs/session-security/`; the browser cases are tracked in
`frontend/tests/session-security.spec.js`. The production build retains its
existing large-bundle warning.

Verification on 2026-10-17 passed 954 Python tests, 197 frontend tests, 10
account/session browser checks and the production frontend build. Browser
artifacts are in `outputs/account-security-verified-browser/`; cases are tracked in
`frontend/tests/account-settings-security.spec.js` and
`frontend/tests/session-security.spec.js`. SQL was validated in isolated local
PostgreSQL schemas, including applying the local migration twice and executing
the hosted migration there. Incremental and consolidated hosted statements
were checked for alignment.

The hosted `account_session_security` migration was applied on 2026-10-17 through
the official project-scoped Supabase MCP connection to project
`lzsopugajopzpwhzxeoj` (hosted migration version `20261017102544`). Follow-up
queries confirmed the session table and three new challenge columns, RLS on
both tables, and no table privileges for the `anon` or `authenticated` roles.
The eight isolated PostgreSQL security checks passed again before application.
No production passwords, recipients or orchard records were changed.

The required `python -m scripts.sync_supabase_schema --apply` command was also
attempted, but could not run because `SUPABASE_DATABASE_URL` is absent from this
laptop's server configuration. The incremental migration was applied using MCP;
the consolidated schema hash was not advanced. Configuring the authorized MCP
connection does not configure the application's separate cloud-backup database
connection. The frontend and running API have not been redeployed by this step.

The hosted table inspection also reported a separate existing permission issue:
`public.spatial_ref_sys` has RLS disabled, and both browser API roles have write
privileges. A follow-up inspection confirmed that PostGIS 3.3.7 is installed in
`public`, and that `supabase_admin` owns the extension and granted these privileges.
The connected `postgres` role is not a member of the owner role and has no grant
option to revoke those grants. No permission change was attempted or applied.

This table contains PostGIS coordinate definitions, separate from MangoPoint's
account and orchard tables. Supabase documents this exact ownership warning in
its [PostGIS troubleshooting guide](https://supabase.com/docs/guides/database/extensions/postgis#security-advisor-flags-publicspatial_ref_sys).
For this backend architecture, disable the unused generated Data API in the
Supabase Dashboard under **Integrations > Data API**, using the **Enable Data API**
switch. The repository uses FastAPI and direct PostgreSQL connections for data;
its optional asset backup uses the separate Storage API. Check for any external
clients outside this repository before disabling the generated Data API. This
dashboard setting has not been changed by Codex. See
[Supabase's Data API guidance](https://supabase.com/docs/guides/api/securing-your-api#disable-the-data-api).

For a permanent extension cleanup, contact Supabase Support to review the
owner-controlled grants or arrange moving PostGIS to a non-exposed schema.
Relocation needs application compatibility checks and a backup plan; avoid
dropping the extension with CASCADE in this live orchard database.

Suggested support request (not sent):

> Project `lzsopugajopzpwhzxeoj` has PostGIS 3.3.7 in `public`.
> `public.spatial_ref_sys` is owned by `supabase_admin`, which granted write
> privileges to `anon` and `authenticated`; our connected role is `postgres`
> without ownership or grant option. Please remove unnecessary browser-role
> write privileges while preserving coordinate lookups, or advise on a
> supported relocation that preserves our existing GIS data and dependencies.
