# Email-login release activation, 2026-10-19

The user pushed `2804e7ed0ddebdbefca65bdcff486ccb68caabcc` to
`mangopoint-production`. Authenticated Vercel inspection confirmed a `READY`
production deployment at
`mango-point-rnmbc368r-luisgabriel27s-projects.vercel.app` for that commit.

The running laptop API was healthy but its public schema still lacked
`/auth/login/verify`. The process listening on port 8000 was verified as this
checkout's `.venv` Python launcher running `run_server.py --host 127.0.0.1
--port 8000`. That old API process was stopped, then `start_production.bat`
started the updated API in the background and checked the production connection.

Executed checks after restart:

- Local `/health`: `healthy`, database `connected`.
- Local OpenAPI: `/auth/login/verify` and `/auth/login/resend` both present.
- Shared site's `/api/health`: `healthy`, database `connected`.
- Shared site's `/api/openapi.json`: both new login endpoints present.
- The production launcher confirmed public health, browser access, login
  preflight and the existing published `/api` route. Startup checks completed
  in 27.5 seconds. No frontend redeployment or API route change was needed.

These checks establish that the deployed frontend and running API now expose
the matching email-code flow. No login was submitted or verification email
requested during these checks. Real inbox delivery and the authenticated user journey
remain to be checked by a normal sign-in; manual workflow cases remain Not run.
Existing sessions keep their normal expiry rules, so sign out before testing
the new login step. Refresh the online frontend if a browser retains an older
loaded page.

No application source or hosted Supabase schema was changed during activation,
and no account records were manually edited. Normal API startup and configured
background services resumed. The server laptop, database and tunnel must remain
running. Earlier
implementation checks and their pre-release state are recorded in the
[implementation report](email-login-security-2026-10-19.md).
