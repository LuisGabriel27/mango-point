# Session recovery production release — 2026-10-20

The user's screenshot showed the deployed login page's two-session error without
a recovery button. Read-only checks confirmed that the deployed frontend asset
`assets/index-vYAQrNog.js` contained neither recovery control. Both the running
local API and public `/api/openapi.json` also lacked the recovery request and
response fields. The earlier implementation had been tested locally and had not
yet been deployed.

The verified background Python API was restarted using the same project virtual
environment, host, port and database. Its initial restart guard refused to stop
the process because Windows runs the virtual-environment launcher and Python
interpreter as separate processes. Both commands and the port owner were verified
before the actual restart. No account session reset was performed as a release
step, and no database schema changes were needed.

`start_production.bat -ForceDeploy` then published the reviewed frontend from the
current workspace. The launcher confirmed that the existing `/api` route already
pointed at this server, retained that route, restored the Vercel project root to
`frontend`, and passed public API/database/login-access checks. Startup/release
checks completed in 115.7 seconds.

- Production URL: [MangoPoint](https://mango-point-projects.vercel.app).
- Deployment: [mango-point-nzylhhobw-luisgabriel27s-projects.vercel.app](https://mango-point-nzylhhobw-luisgabriel27s-projects.vercel.app),
  `READY`, target `production`.
- Published frontend asset: `assets/index-COBQucHB.js`; it contains **Email a
  recovery code**, **Sign out other sessions and sign in**, and the issuing-API
  session-pinning key.
- Both local and public APIs returned healthy/connected status and advertised
  `LoginRequest.recover_sessions` and `LoginChallengeResponse.session_recovery`.

Headless Edge loaded the actual production assets at 1440px and 390px. Isolated
browser responses supplied a two-session error and a recovery challenge. Both
widths showed the recovery button and explicit confirmation; filling all six
digits sent no verification request. Screenshots and credential-free results
are retained in `outputs/session-release-2026-10-20/`. The smoke checks sent no
real sign-in, recovery-verification or email requests and changed no farm records.
They establish deployed UI availability and API capability, not a completed
recovery against a real account/inbox. The affected-device email/recovery and
physical network-disconnection rehearsals remain pending.

The source had already passed 997 Python checks, 214 frontend checks, 35 browser
cases and its production build during implementation. Those full suites were
not rerun for this deployment-only step. Changed-document local links, workflow
CSV structure and `git diff --check` were checked afterward. See
[recovery implementation verification](session-slot-recovery-2026-10-20.md) and
[offline-session verification](offline-session-recovery-2026-10-20.md).

An already open tab keeps its loaded JavaScript until it reloads. Refresh online
(Ctrl+Shift+R if necessary), submit the password again, and use **Email a recovery
code** if both slots are occupied. Fresh recovery still requires the API and
working mail delivery; it signs out all other sessions only after explicit code
confirmation.

This was a manual production release from the reviewed local workspace. No Git
commit or push was performed; the source changes remain in the working tree.
Include them in the next reviewed Git release so a later automatic deployment
does not replace this fix with older source. Existing unrelated worktree changes
were preserved. No Supabase schema update was required or attempted.

Later on 2026-10-20, the recovery guidance was shortened to: “Verify your email
to sign out other sessions and sign in here.” All 214 frontend checks and the
production build passed, then the frontend was republished with the same release
workflow. Public asset `assets/index-Bz0KAdWi.js` contains the shorter message
and no longer contains the previous paragraph. Verification is recorded in
`outputs/session-copy-2026-10-20/release.json`. No API restart or schema change
was needed for this copy edit; full backend/browser suites were not rerun.

The guidance and email-code action were subsequently moved into a modal and
republished as `assets/index-DLxH9K2M.js`. See the
[modal verification and release](session-recovery-modal-2026-10-20.md) for its
desktop/mobile dismissal, focus, retry and production-asset checks.
