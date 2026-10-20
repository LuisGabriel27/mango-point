# Recovery modal — 2026-10-20

The two-session recovery explanation and **Email a recovery code** action now
appear in the existing confirmation modal. A normal capacity error opens **Two
sessions are active** with the short message: “Verify your email to sign out
other sessions and sign in here.” The repeated inline banner is removed.

Cancel, Escape, close and backdrop dismissal preserve the entered username and
password. Focus returns to **Recover account access**, which reopens the modal.
The open modal keeps keyboard focus inside, makes the background inert and locks
body scrolling; dismissal restores the page. Initial focus is on Cancel.

Requesting a recovery code uses the same API and existing backend. Mail errors
remain inside the modal for retry. Successful delivery closes it and opens the
existing six-digit code screen. If slots fill during normal code verification,
the user returns to password entry and can open recovery after re-entering the
password. Opening or dismissing the modal does not request email or revoke any
session; revocation still requires explicit confirmation of a valid emailed code.

No backend, simulation, database schema or cloud-sync behavior changed. Prior
release evidence and unrelated existing worktree changes are retained. Browser
checks use isolated API responses and send no real email or farm/account writes.

Verification on 2026-10-20 passed all 214 frontend checks, the production build
and 25 isolated Edge browser cases: seven recovery/modal cases, 14 email-login
cases and four account-settings cases. The existing build-size warning remains.
The backend suite was not rerun for this frontend presentation change. Modal
screenshots and results are retained in
`outputs/session-recovery-modal-2026-10-20/`; the 390px modal screenshot was
visually inspected. WF-97 in the workflow results records the executed dismissal,
focus, preserved-input and error/retry rehearsal.

The frontend was published with `start_production.bat -ForceDeploy`; the launcher
reused the healthy API and existing route and completed its release checks in
105.8 seconds. Published asset `assets/index-DLxH9K2M.js` contains the modal and
reopen control. Edge then loaded the actual production assets at 1440px and
390px with intercepted auth responses: the modal, initial Cancel focus,
Cancel/reopen without a recovery request, and the explicit code screen all
passed. No real email or account recovery was performed by these checks.
Release metadata, screenshots and browser results are retained in
`outputs/session-recovery-modal-release-2026-10-20/`. An existing open page needs
an online reload to receive the modal. Source changes remain uncommitted, as
described in the [production release record](session-recovery-production-release-2026-10-20.md).
