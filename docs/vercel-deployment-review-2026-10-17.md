# Vercel deployment review, 2026-10-17

MangoPoint's frontend is served by Vercel. The application's FastAPI service and
PostgreSQL database run on the server laptop. The frontend calls the fixed
`/api` address, whose project-level Vercel rewrite points to the laptop's public
tunnel. Supabase's generated Data API is separate from this application API;
disabling the unused Data API adds no MangoPoint sign-in step.

## Confirmed findings

- The local branch and GitHub branch `mangopoint-production` both point to
  `032aa7719efb07fe9fb8511fbc1f9adf1dbc0aa7`.
- GitHub reports a successful Vercel deployment for that commit:
  [deployment details](https://vercel.com/luisgabriel27s-projects/mango-point/9ACReeMUHub3AqbUasYMzEFu7G2K).
- Fresh HTTP requests returned different frontend bundles:

  | URL | JavaScript entry |
  | --- | --- |
  | `https://mango-point-projects.vercel.app` | `/assets/index-D4pUGIpl.js` |
  | `https://mango-point-git-mangopoint-production-luisgabriel27s-projects.vercel.app` | `/assets/index-Dow69G8F.js` |

  This difference exists in the HTTP responses, independently of a browser's
  service-worker cache. It establishes that the URLs currently serve different
  builds; it does not by itself identify which Vercel setting caused it.
- GitHub's default branch is `Testing---jl`. Authenticated Vercel inspection
  confirmed that the actual production branch is **`main`**. Git-triggered
  deployments are enabled and the Vite root directory is correctly `frontend`.
  Pushes to `mangopoint-production` therefore build previews, rather than
  replacing the production deployment.
- The shared URL is a manual alias pointing to
  `dpl_89b2CpYsjjH4Tj2CJDVjQoTgSWvV`, a CLI production deployment whose recorded
  Git commit is `9c25de02788ea079e3cd7be781c95451358c4027`. It is not registered
  as a managed project domain. The only managed domain returned by Vercel is
  `frontend-psi-pearl-qawkssxbqc.vercel.app`.
- The successful latest branch deployment is
  `dpl_9ACReeMUHub3AqbUasYMzEFu7G2K`, serving
  `mango-point-a82cq4s2u-luisgabriel27s-projects.vercel.app`. It is ready and has
  no production target. Both branch tracking and shared-domain assignment need
  correction for pushes to update the shared website automatically.
- Normal `start_production.bat` startup reuses a healthy API and an existing
  frontend that uses `/api`. It does not fetch new Git commits, rebuild a healthy
  API container, or publish frontend changes just because code was pushed.
- `start_production.bat -ForceDeploy` explicitly builds the local frontend,
  deploys it and assigns `mango-point-projects.vercel.app` to that deployment.
  A manually assigned alias needs verification against the project's managed
  production domains when diagnosing automatic releases.
- The new account-security changes remain uncommitted in this checkout.
  Git-based builds cannot include them until they are committed and pushed.
- This laptop has neither a root nor a frontend `.vercel/project.json` link.
  The user completed device authorization and the CLI confirmed the
  `luisgabriel27` account. Authenticated project, alias and domain reads were
  used for the findings above. No deployment or production settings were changed
  during this review.

## Recommended Vercel configuration

In the `mango-point` project, set **Settings > Environments > Production >
Branch Tracking** to `mangopoint-production`. Keep the root directory as
`frontend`. Register `mango-point-projects.vercel.app` under the project's
**Domains** so it follows production deployments, rather than remaining only
an alias on one deployment. Before publishing, check the production
`VITE_API_BASE=/api` configuration and the project's API rewrite, then build and
release the intended committed version to production. Do not deploy the
uncommitted security changes until their matching API release is ready.

## Release workflow

With a working Vercel Git integration, pushes to the configured production branch
create production builds; pushes to other branches normally create previews.
The production branch and the shared URL's domain assignment need to agree.
Confirm the Git repository, production branch, frontend root directory,
production API-base configuration, latest production deployment, and shared
domain assignment in Vercel before changing them.

Backend updates require the server laptop to pull the committed code and restart
the updated API. For the Docker setup, rebuild/recreate the API after pulling:

```powershell
docker compose up -d --build --no-deps api
```

Then run the launcher to verify the database, tunnel and `/api` routing. Merely
refreshing a page or rerunning normal startup does not replace an old API image.
Deploy backend and frontend together for changes that introduce new endpoints.

References: [Vercel Git deployments](https://vercel.com/docs/git),
[production branch configuration](https://vercel.com/docs/git#customizing-the-production-branch),
[Vercel aliases](https://vercel.com/docs/cli/alias).
