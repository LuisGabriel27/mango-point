# Deployed remote login check — 2026-10-11

The reported login failure was traced to a changed Cloudflare Quick Tunnel.
The production JavaScript contained
`https://pieces-larry-buses-dock.trycloudflare.com`, while the running
cloudflared metrics reported
`https://following-functions-merry-lake.trycloudflare.com`.
The local API and database were healthy. The active tunnel's health check
returned healthy/connected and its login preflight accepted
`https://mango-point-projects.vercel.app`.

The production `VITE_API_BASE` was updated and the frontend rebuilt. The
existing Vercel project root was restored to `frontend`, and the clean alias
was assigned to the successful deployment.

## Executed browser check

- Site: https://mango-point-projects.vercel.app/login
- Browser: Microsoft Edge, headless, isolated fresh context.
- All requests to http://127.0.0.1:8000 were explicitly blocked to emulate a
  visitor without a local MangoPoint companion.
- The actual sign-in form used the existing configured account. Credentials
  were passed in memory; no screenshots, traces, passwords or tokens were
  written to the evidence.
- Login request: HTTP 200 from the active public tunnel.
- The browser navigated to the dashboard and its Logout control was visible.
- Visible exact “Network Error” messages: 0.
- Failed remote requests: 0.
- Browser page errors: 0.

This verifies the shared remote login path. The groupmate's own device was
not controlled or tested. No simulation, field verification or biological
validation case was executed as part of this check.

## Restart workflow

`start_remote_access.bat` detects an existing Quick Tunnel or starts one,
checks health and CORS, and updates/redeploys Vercel when its compiled remote
address differs. Its `-CheckOnly` path was executed successfully against the
active tunnel and live frontend. Its `-ForceDeploy` path also completed
successfully: production environment update, frontend build, project-root
restoration, clean-domain alias, and final public bundle/health/CORS checks.
The isolated browser login check was repeated after this publication.
Quick Tunnel addresses remain temporary; the server laptop and API must
remain running and online.
