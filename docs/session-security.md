# Session security

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

Each token contains a keyed HMAC derived from the account ID and stored password
hash. The raw password and password hash are never included in a token. The API
compares this stamp against the current account on every authenticated request.
Changing or resetting the password changes the stored hash, immediately making
all old tokens invalid across devices and API workers. Profile/name/email changes
do not invalidate this stamp. A wrong current password changes no credentials.
The existing offline default-admin fallback cannot recover into a persisted
account whose password has changed away from its configured default.

After a successful password change, the current browser clears its session and
shows Login with instructions to use the new password. Other connected devices
sign out on their next authenticated request or session check, normally within
30 seconds while visible. Hidden tabs check when they resume. A response from a
previous session cannot restore authentication after logout or replace a newer
login. Session maintenance creates no orchard, forecast or field records.

Deploy both the frontend and backend, then restart the API. Legacy tokens lack
the new credential stamp and require a fresh sign-in. No database schema change
or hosted Supabase update is required. Ordinary manual logout still discards the
device's token; issued tokens have the bounded lifetime described above.

Automated checks use isolated accounts, mocked database sessions and intercepted
browser API responses. They verify timeout/renewal, preserved inactivity across
reloads and suspended tabs, password change/reset revocation, invalid-password
handling and late-response protection. They do not change production passwords
or establish pest prediction accuracy. Real deployment rehearsal remains in
WF-74 through WF-77 of the [manual test plan](manual-workflow-test-plan.md).

Verification on 2026-10-13 passed 877 Python tests, 194 frontend tests, four
session browser checks, 16 Verify/tutorial browser regression checks and the
production frontend build. Local execution logs are in
`outputs/session-security/`; the browser cases are tracked in
`frontend/tests/session-security.spec.js`. The production build retains its
existing large-bundle warning.
