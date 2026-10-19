# Email-code sign-in implementation, 2026-10-19

The working-tree implementation requires the account password and an emailed
code before creating a new MangoPoint session. It uses the existing FastAPI
authentication boundary, PostgreSQL challenge/session tables and configured
Brevo/SMTP transport. No new dependency or database schema is required.

## Behavior

- `POST /auth/login` accepts the username/email and password. Correct credentials
  request a purpose-bound `login` challenge, not an access token or session slot.
- `POST /auth/login/verify` checks the challenge and code before issuing a token.
  The code expires in five minutes, allows five incorrect attempts and can be
  successfully used once. Both credential and code checks require an active
  account. Pending codes are invalidated by a password or email change.
- `POST /auth/login/resend` requires the pending challenge and enforces a
  60-second per-account login-code cooldown. A successful resend consumes older
  login challenges; failed email delivery rolls back the replacement and leaves
  the earlier still-valid code available.
- Account/challenge locks serialize verification, attempts and session allocation.
  The two-session limit is checked before requesting a code and at confirmation.
  Correct codes are consumed even when a session slot fills before confirmation.
- Login and account-recovery codes have separate purposes. Neither can be
  exchanged for the other flow. Codes are hashed, omitted from API responses,
  sign-in email subjects and application logs, and excluded from cloud backup.
- The login page provides a masked inbox, code entry, resend countdown, expiry
  guidance and Start again. It clears the password after the first step and
  keeps pending state in memory. It creates no browser session before successful
  verification and rejects password-only responses from an older API.
- Verification/resend use the API that issued the challenge even if companion
  availability changes. Leaving the login screen or ending a session invalidates
  pending browser authentication, so a late response cannot restore access.
- An existing verified session retains its normal inactivity, absolute expiry,
  refresh and logout rules. New sign-ins require working email delivery even on
  a local companion. There is no password-only offline fallback.

## Verification

Executed against the working-tree implementation:

- Full Python suite: **965 passed**, with one existing Starlette/httpx deprecation
  warning. PostgreSQL security checks use temporary schemas and mocked email
  transport; application accounts and records are not modified by those tests.
- Targeted Python security checks: **32 passed**, including concurrent attempts
  and replay, expiry, inactive accounts, credential/inbox changes, purpose
  separation, failed delivery/resend rollback and session capacity rechecking.
- Frontend unit suite: **198 passed**. The production build passed with the
  existing large-chunk warning. Results are recorded in
  `outputs/email-login-frontend-tests-final.log` and
  `outputs/email-login-frontend-build-final.log`.
- Isolated email-login browser suite: **8 passed**, in
  `frontend/tests/email-login.spec.js`.
  They intercept all application API requests and email codes. Initial checks
  identified a missing focus transition; the verification form now mounts with
  the code input focused. The final focused run verifies keyboard and narrow
  layout behavior, partial sessions, resending, expiry, API pinning, mail failure,
  old API rejection, loss of the issuing API without fallback, and late-response
  cancellation. Results are in `outputs/email-login-browser-final.log`.
- Existing isolated session/account browser regressions: **10 passed**, using
  the two-step login fixture. Results are in
  `outputs/email-login-session-browser-final.log`.
  Live production/companion connection tests now accept an existing
  verified session token rather than automatically sending login emails.

Read-only local readiness checks found Brevo transport configured, one active
account and zero detected placeholder inboxes. This checks configuration and
placeholder patterns, not mailbox ownership or actual delivery. No private
addresses, credentials, tokens or codes were printed by that check.

No real verification email was sent, no production login was attempted and no
manual workflow cases were marked Pass. New cases WF-78–WF-83 remain **Not run**
in the [manual results](manual-workflow-test-results.csv). Historical evidence
from older password-only sign-ins remains preserved and does not establish
email-login validation. See the [manual plan](manual-workflow-test-plan.md).
Changed documentation links, results CSV structure and `git diff --check` passed.

## Release state

These source changes have not been committed, pushed, deployed to Vercel or
activated by restarting the running API. Read-only inspection of the running
local API confirmed it still lacks `/auth/login/verify`. Update the matching
frontend and backend together; an old frontend cannot complete the new pending
challenge response, and the new frontend refuses a password-only backend.

Before release, confirm a reachable saved inbox for every active account and
working mail configuration on each authoritative API. After release, execute
the dedicated test-account inbox checks. A placeholder or inaccessible inbox
requires controlled administrator recovery; changing `.env` does not overwrite
an existing account's address. No account emails were changed by this work.

The hosted Supabase schema was not changed. The existing migration and consolidated
schema already support the `login` purpose string and binding fields, so no hosted
schema synchronization was needed. The existing modified `sites/mangopoint-access`
submodule and deployment-preparation edits were preserved.
