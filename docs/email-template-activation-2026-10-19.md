# Email template activation — October 19, 2026

The reported phone and desktop screenshots showed the old red-bordered pest
alert without the new branded header. The native API listener was still the
process started before the redesigned email files were written.

## Diagnosis and activation

- The old listener was PID 30144, with launcher PID 31036. Both command lines
  identified this repository's `.venv\Scripts\python.exe` running
  `run_server.py --host 127.0.0.1 --port 8000`.
- `api/services/notification_service.py` was updated at 14:10:38 and
  `api/services/email_templates.py` at 14:13:17, after the old API started.
- Building a synthetic alert MIME message in a fresh Python process confirmed
  the new `ORCHARD MONITORING` header and mango image URL were present, and the
  former red top-border markup was absent. This check did not send the message.
- After verifying the exact process commands, the stale API and its launcher
  were stopped, and `start_production.bat` started their replacements.
- The replacement listener is PID 25044 (launcher PID 41408), created at
  **2026-10-19 14:20:14 +08:00**, after both email files were updated.

The startup script normally reuses a healthy API. Running it while the old
listener remained active would therefore not have reloaded the templates.

## Verification

- Template and notification tests: **20 passed**. Log:
  `outputs/email-template-activation-tests-2026-10-19.log`.
- Local API health: healthy, database connected.
- Published `https://mango-point-projects.vercel.app/api/health`: healthy,
  database connected.
- Startup checks completed successfully, including the deployed `/api` route
  and login access checks. The existing route already used this server, so no
  frontend deployment or route change was required.

No application code or database schema was changed during this activation.
The email redesign remains local and uncommitted/unpushed. The running laptop
API loads the local source. Existing user files and the access-site submodule
were preserved.

No test email or sign-in request was submitted by these checks. Normal server
background services resume when the API starts. A newly generated email still
needs to be inspected in the actual inbox; this record does not claim a Gmail,
Apple Mail or Outlook rendering pass. Previously received emails retain their
original HTML. A new sign-in verification code can be requested through the
normal application flow to check the redesigned header and mango logo.
