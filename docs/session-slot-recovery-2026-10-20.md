# Session-slot recovery — 2026-10-20

The user reported being unable to sign in after closing both permitted browser
sessions without logging out. The API still held two valid session records,
and a third login was rejected until expiry. Baseline code confirmed there was
no owner recovery route on the login screen.

The two-session limit remains. After a correct password receives the full-session
message, the user can choose **Email a recovery code**. This requests a separate
`login_recovery` challenge from the same API, including if companion availability
changes. The password is cleared after the challenge is received. The recovery
email and screen explain that confirmation signs out all other sessions for
that account and may discard unsaved work in them.

Recovery requires entering the emailed code and explicitly choosing **Sign out
other sessions and sign in**. Completing the code does not submit automatically.
Normal sign-in retains automatic verification. **Start again** returns to password
entry. A session-capacity conflict during ordinary verification also returns to
password entry with recovery available.

The backend verifies the password before sending the code. It verifies the
challenge's purpose, account, credential stamp, inbox, expiry, consumption and
attempt limit before revoking sessions. Revocation and replacement session
allocation occur in one transaction under the same account lock used by normal
login and renewal. Replayed codes and in-flight renewals cannot restore revoked
sessions. Recovery affects only the same account on that API/database. It leaves
one active session; a second normal login is still allowed and a third is blocked.

Ordinary and recovery challenges share the login-code cooldown and replace
earlier pending challenges in either flow. Resend preserves the purpose.
Requesting/resending a code, failed delivery, cancellation or invalid verification
does not revoke existing sessions. A normal login code cannot become recovery
through an extra verification-request flag. Existing idle and absolute expiry
rules remain. Fresh recovery requires a reachable API and working email delivery.

This follows OWASP's guidance to let users terminate other sessions after
authentication. [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).

The existing `VARCHAR(20)` purpose column supports `login_recovery`; no database
schema was changed. No hosted schema update was required or attempted. The
simulation engines, model and cloud-sync service are unchanged. Earlier offline
session changes and unrelated existing worktree changes were preserved.

Verification uses intercepted Edge browser API responses, mocked email delivery
and fresh isolated local PostgreSQL schemas. It does not send real mail or change
production sessions, accounts or farm records. Browser controls and backend
revocation are separate checks. Deployment was pending at initial verification;
the API/frontend were subsequently
[released on 2026-10-20](session-recovery-production-release-2026-10-20.md).
Affected-device rehearsal remains pending; these checks do not establish real
mail delivery or pest accuracy.

Verification completed on 2026-10-20:

- `.venv\Scripts\python.exe -m pytest -q`: all 997 checks passed, including real
  PostgreSQL recovery, revocation, code replay, expiry, credential/inbox/account
  changes, delivery rollback and concurrent recovery/renewal. The existing
  Starlette TestClient deprecation warning remains.
- `npm.cmd test`: all 214 frontend checks passed.
- 35 isolated Edge browser cases passed: five recovery cases, 14 email-login
  cases, ten offline-session cases and six existing session-security cases.
- Production frontend build passed with its existing large-bundle warning.
- Changed-document local links, workflow CSV structure and `git diff --check`
  passed. WF-92–WF-95 and SESSION-002 record the executed fixture rehearsal.

Final browser results and desktop/mobile confirmation screenshots are under
`outputs/session-slot-recovery-2026-10-20/final-results.json` and
`final-artifacts/`. The initial `results.json` and `artifacts/` remain available:
an old keyboard expectation needed to include the new Start again control;
a session-cleanup race recreated the activity timestamp after sign-out; and
an initial mobile logout-focus assertion failed. The final run passed all cases.
The cleanup fix stops the session monitor synchronously before clearing storage,
with a regression that dispatches focus in the same task before React cleanup.
The initial Python run also identified a fixture cooldown helper that advanced
only normal login challenges; it now handles both login purposes. The final full
suite passed after that fixture correction. Frontend tests used approved execution
outside the sandbox because esbuild needs parent-directory traversal.
