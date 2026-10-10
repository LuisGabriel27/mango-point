# MangoPoint Codex instructions

## Project and scope

- MangoPoint is a FastAPI and React/Vite orchard pest simulation application
  with cellular automata (CA) and tree-to-tree graph engines. The pest scope is
  fruit-attacking Cecid and Oriental Fruit Fly (`Bactrocera dorsalis`). Do not
  broaden Cecid behavior claims to leaf- or flower-attacking midges.
- Read `README.md` for setup and the user workflow. Check
  `core/config.py::SIMULATION_MODEL_VERSION` when reporting the active model;
  the current reviewed baseline is `2026.10-source-progression-v17`.
- Preserve existing user changes and versioned evidence. Do not overwrite
  archived validation outputs or describe an older model's BPI agreement as
  results for the current model.
- The FastAPI backend is the application data boundary. Frontend changes use
  the existing API and authenticated application state.

## Hosted database and credentials

- Use the official, project-scoped `supabase` MCP connection when inspecting or changing the hosted Supabase project.
- Treat `supabase/migrations/*.sql` and `supabase/MangoPoint_Supabase_SQL_Editor.sql` as the source of truth for hosted database changes. Keep both forms aligned whenever the schema changes.
- Validate schema SQL locally before updating Supabase. Then run `python -m scripts.sync_supabase_schema --apply` and report whether the hosted schema changed.
- Never place Supabase database URLs, access tokens, service-role keys, or OAuth credentials in tracked files or frontend environment variables.
- Application code and UI-only changes do not require a Supabase schema update. Local durable data continues to synchronize through the existing cloud-sync service.

## Model and output interpretation

- Read `docs/v17-model-readiness-review.md` before changing source progression
  or explaining current spread outputs. Fruit Fly initial adult source
  pressure is separate from new fruit damage; newly infested trees must not
  become new adult sources within the same forecast.
- Cecid local emergence/movement uses finite source cohorts, laying capacity
  and stage/moisture/light/rain gates. Cloud percentage or canopy shade alone
  must not be described as sufficient emergence/movement conditions.
- Outside Cecid pressure is an assumed directional exposure proxy; do not
  describe it as tracked boundary arrivals with measured travel times, ages
  or egg depletion. The local movement limit does not constrain that proxy.
- Separate repeated-run infestation frequency from a representative run,
  modeled risk from observed infestation, and crop-impact estimates from
  measured farm benefits. Preserve weather provenance, model version and
  scenario assumptions in saved outputs and reports.
- Keep monthly BPI comparison, automated verification, controlled simulation
  experiments and prospective field validation distinct. Current v17 BPI
  evaluations are pending; archived v16 agreement is version-specific.

## Planned React Joyride tutorial

The tutorial is planned in `README.md`; it is not implemented. The current
documentation request explicitly defers React work. Do not install
`react-joyride`, edit frontend code/styles or start implementation as part of
documentation preparation. When the user requests implementation, proceed
within that request using the following guidance; this note does not require
an additional confirmation after implementation is authorized.

- Follow the existing Setup → Simulate → Results → Verify workflow, with
  History/exports and explanations of the other dashboard views. Use the real
  labels and controls; do not invent a Save Run button or demo result.
- Provide a visible way to start/replay the tutorial, a dismissible first-use
  invitation, Back/Next, Skip/Close and progress feedback. Keep text short and
  useful to farm users; omit implementation details from tutorial copy.
- Read the selected release's official documentation at
  https://react-joyride.com/docs/getting-started and verify React 18 support.
  Match imports, props, events and lifecycle handling to the installed
  version. Do not mix examples from incompatible Joyride releases.
- Keep step definitions and lifecycle handling in a focused module/component
  integrated with dashboard state. Add stable, descriptive `data-tour`
  attributes or equivalent identifiers; do not depend on incidental styling
  classes, text matching or array positions.
- Prepare the correct tab/workspace and visible target before showing a
  step. Use the selected Joyride version's lifecycle/readiness mechanisms;
  avoid arbitrary timeout chains or a forced externally controlled index
  where normal lifecycle handling suffices.
- Treat no-result, loading/error, saved-result and role-restricted states
  explicitly. Offer useful guidance or skip unavailable steps without hanging
  or manufacturing outputs. Do not run a forecast to create a tutorial target.
- Tutorial navigation may change presentation state. It must not mutate
  orchard/scenario inputs, write orchard/observation/alert/account records,
  submit simulations, trigger sync, send notifications, change recipients,
  resolve alerts or initiate exports.
  Users carry out those actions through the normal application controls.
  Ordinary read-only loading on a tab change is acceptable.
- Preserve unsaved user input and results. Handle orchard changes and logout
  without stale targets. Clean up overlays, focus and temporary navigation
  state on Skip/Close/Finish so normal use remains possible.
- Keep overlay/focus behavior compatible with the existing sidebar, map,
  dialogs and mobile layout. Test keyboard navigation and tooltip placement.
- Scope any optional completion/dismissal preference to the signed-in user
  and tutorial version, handle unavailable browser storage gracefully, and
  retain manual replay. A tutorial preference does not require a new hosted
  database schema.
- When shipped, update README status, dependency instructions and test
  evidence to describe the implemented behavior accurately.

## Verification and workflow testing

- For documentation-only edits, check content, local links and
  `git diff --check`; do not report application tests as freshly executed.
- For frontend changes, run `npm.cmd test` and `npm.cmd run build` from
  `frontend/`. Use `npm.cmd` in PowerShell if `npm.ps1` is blocked.
- For backend/model changes, run the relevant Python checks with
  `python -m pytest`; use the full suite when changes affect shared engine/API
  behavior. Refresh affected controlled/historical evidence for model changes.
- Use `docs/manual-workflow-test-plan.md`,
  `docs/manual-workflow-test-results.csv` and
  `docs/manual-workflow-bug-log.csv` for actual browser rehearsal. Test both
  pests and engines. Only mark a case Pass after executing it; record reasons
  for Blocked/N/A and reproduction steps for Fail.
- For Joyride implementation, verify start/replay, Back/Next,
  Skip/Close/Finish, conditional/missing targets, no-result and saved-result
  states, orchard switching, logout, failures, keyboard use and narrow layout.
  Verify that tour navigation changes no saved orchard, observation, alert or
  account records, triggers no automatic simulation/notification requests,
  and leaves the normal workflow usable. Optional local tutorial preferences
  are permitted as described above.
- Prefer meaningful lifecycle/regression checks over tests that duplicate
  tooltip wording. Do not create fake observations, validation passes or bug
  reports to demonstrate the tutorial.
