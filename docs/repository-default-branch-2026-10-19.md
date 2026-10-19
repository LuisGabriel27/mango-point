# Repository default branch, 2026-10-19

The GitHub default branch for `LuisGabriel27/mango-point` is now
`mangopoint-production`, matching the existing Vercel production branch.
The branch keeps its name; the separate `main` and `Testing---jl` branches
were not renamed, deleted or merged.

## Applied change and verification

- The authenticated GitHub repository API changed `default_branch` from
  `Testing---jl` to `mangopoint-production`. A subsequent API read and the
  connected GitHub app both confirmed the new default.
- The production branch commit remained
  `490f05254681e7c3ba3dae77680b81ad4bfc019d` throughout the change.
- `git remote set-head origin -a` updated this checkout's `origin/HEAD` from
  `origin/main` to `origin/mangopoint-production`.
- Live Vercel inspection confirmed the `mango-point` project's Git integration
  is enabled, its production branch is `mangopoint-production`, its root is
  `frontend`, and automatic production domain assignment is enabled.
- The latest inspected production deployment,
  [`dpl_3SVVeyaomzz6bEztjMmZSNn6Pkmc`](https://vercel.com/luisgabriel27s-projects/mango-point/3SVVeyaomzz6bEztjMmZSNn6Pkmc),
  is `READY`, has source `git`, and identifies that same branch and full commit.
  Its assigned aliases include `mango-point-projects.vercel.app`. The shared
  address is also verified as a managed project domain without a preview-branch
  assignment. This confirms a Git-triggered production release since the
  [initial deployment setup](automatic-production-deployment-2026-10-19.md).

No source commit, push or new deployment was created for this configuration
change. Existing uncommitted work was preserved. Documentation content, local
links and `git diff --check` were checked; application tests and browser
workflow tests were not rerun.

## Developer workflow

Use `mangopoint-production` as the team's integration and release branch.
Feature branches can be merged through pull requests, which now target this
branch by default. Review and test changes, commit only the intended files,
then push or merge to `mangopoint-production`:

```powershell
git push origin mangopoint-production
```

Vercel automatically builds the committed frontend and updates
<https://mango-point-projects.vercel.app> after a successful production build.
Local saves, local commits and pulls do not deploy. Other branches produce
previews. Visitors receive the new interface when they open or reload the
online app; an already loaded or offline page can retain its current release.

FastAPI, the simulation engine, database and tunnel still run on the server
laptop. Backend changes require updating and restarting that service as
described in [the README](../README.md#sharing-the-deployed-app-with-another-laptop).
This branch setting does not automate backend deployment or remove the need
to keep the server laptop running.

References: [GitHub default branch](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-branches-in-your-repository/changing-the-default-branch),
[Vercel Git deployments](https://vercel.com/docs/git).
