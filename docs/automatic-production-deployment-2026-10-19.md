# Automatic production deployment, 2026-10-19

MangoPoint's Vercel frontend now follows pushes to `mangopoint-production` in
`LuisGabriel27/mango-point`. The existing shared address,
`https://mango-point-projects.vercel.app`, is a verified managed production
domain, so successful production deployments update that address automatically.

## Configuration applied

Authenticated inspection confirmed the findings in the
[2026-10-17 deployment review](vercel-deployment-review-2026-10-17.md): the
production branch was `main`, and the shared address was assigned to an older
deployment without being a managed project domain. The newly pushed commit
`e68d1ae632e4fbcf666b3d893c19757efb16c09b` had built successfully as a preview.

The existing `mango-point` project was updated as follows:

| Setting | Verified value |
| --- | --- |
| Git repository | `LuisGabriel27/mango-point` |
| Production branch | `mangopoint-production` |
| Git deployments | `enabled` |
| Root directory / framework | `frontend` / Vite |
| Automatic production domain assignment | Enabled |
| Shared production domain | `mango-point-projects.vercel.app`, verified, no preview branch assignment |
| Production `VITE_API_BASE` | `/api` |
| Published `MangoPoint API` rewrite | `/api/(.*)$` to the existing laptop's HTTPS tunnel |

The API rewrite and production API-base value were inspected and retained.
The Git repository's default branch was not changed. Credentials and local
Vercel project links remain outside tracked files.

## Release and executed checks

The existing Git-built preview for commit `e68d1ae` was rebuilt using the
production environment with `vercel redeploy --target production`. This used
the committed source, including the group's pulled changes. No new Git commit
or push was created for this check.

- [Production deployment](https://vercel.com/luisgabriel27s-projects/mango-point/F7fF5vxMVDKv2xZjyTWZBP8WHevU):
  `dpl_F7fF5vxMVDKv2xZjyTWZBP8WHevU`, `READY`, target `production`.
- GitHub branch inspection confirmed the same full commit SHA. Vercel's release
  metadata identifies `mangopoint-production` and that SHA.
- Vercel confirmed the shared URL points to the new deployment, with aliases
  assigned. Fresh public HTTP requests returned 200 for `/` and `/login`.
- Both the public HTML entry and Vite manifest identify
  `/assets/index-CXP1hYj0.js`, matching the production build log.
- Public `/api/health` returned `healthy` with database `connected` before and
  after the release. The public OpenAPI schema includes the new account code,
  session-refresh and logout routes. These reads do not establish a completed
  authenticated account-security workflow.
- `npm.cmd test` in `frontend/`: **197 passed, 0 failed**. An initial sandboxed
  run could not read directories required by esbuild; the successful rerun used
  normal filesystem access.
- `npm.cmd run build` in `frontend/`: passed. Vite reported its existing large
  chunk warning. The Vercel production build also completed successfully.
- Documentation local links and `git diff --check` were checked.

This verifies the configured Git trigger, production build, domain assignment,
served assets and API availability. A subsequent push after the configuration
change has not been exercised. No browser workflow cases were marked Pass,
and no simulations, field records, notifications or account changes were made.
No application code or database schema was changed by this deployment setup;
no Supabase schema update was performed.

## Team workflow and limits

Push or merge reviewed frontend changes to `mangopoint-production`. Vercel builds
them and assigns a successful production release to the shared URL. Other
branches produce previews. Check the Vercel deployment status if a release fails;
the failed build does not establish that the newest commit is live. Pulling the
repository locally is independent of Git-triggered deployment.

The FastAPI process, Python engine and database still run on the server laptop.
This setup does not automatically pull or restart that backend. Pull the
matching code and restart the running API, or rebuild/recreate the Docker API
with `docker compose up -d --build --no-deps api`, then run
`start_production.bat` to verify connectivity. Changes that add API endpoints
need a coordinated backend release. Keep the server laptop and tunnel online.

Visitors load the latest interface when they next open or reload the online
site. An already loaded page is not forcibly refreshed, and an offline PWA can
continue using its cached release until it reconnects.

References: [Vercel Git production branch](https://vercel.com/docs/git#customizing-the-production-branch),
[project domains](https://vercel.com/docs/rest-api/projects/add-a-domain-to-a-project),
[redeploy target environment](https://vercel.com/docs/cli/redeploy).
