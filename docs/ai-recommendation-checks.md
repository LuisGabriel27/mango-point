# Automatic AI recommendation checks

Date: 29 October 2026. Simulation model remains
`2026.10-source-progression-v17`. No engine coefficients or source rules changed.

New successful simulations save their rule-based action plan, then queue optional
Gemini explanations after the response. The dashboard reads the saved guidance
status and displays the explanation at the top of Decision Support. Viewing a
saved run never starts generation. Setup is documented in
[Automatic AI recommendations](../README.md#automatic-ai-recommendations).

## Executed checks

| Check | Result |
|---|---|
| Full Python suite, `python -m pytest -q` in the project virtual environment | 1,022 passed |
| Final focused backend check, `python -m pytest tests/test_ai_recommendations.py -q` | 19 passed |
| Frontend, `npm.cmd test` | 225 passed |
| Browser, `npx.cmd playwright test tests/ai-guidance.spec.js --reporter=list --output=../outputs/ai-guidance-browser-20261029-reviewed` | 8 passed |
| Frontend production build, `npm.cmd run build` | Passed |
| `git diff --check` and README local-link check | Passed |

The full Python suite ran before a small equivalent background-status branch
cleanup; all 19 focused cases were rerun after that cleanup. The frontend suite
and browser launcher needed filesystem access beyond the Windows sandbox for
esbuild to resolve project files. Build output retains the existing large-bundle
warning; Python reports a Starlette TestClient dependency deprecation warning.

[Backend checks](../tests/test_ai_recommendations.py) cover the two pests and
engines, missing/disabled configuration, minimized provider context, header-based
authentication, JSON validation, matching action references, incomplete output,
provider failures, concurrency limits, expired jobs, persistence, deleted runs,
authenticated status reads and generation queued after local forecast saving.

[Frontend polling checks](../frontend/src/utils/aiGuidance.test.js) cover bounded
polling, terminal states, authentication/network failure, wrong-run responses and
cancellation. History regressions cover pending-guidance reconciliation and a
late pending snapshot arriving after completed guidance was cached.

[Browser checks](../frontend/tests/ai-guidance.spec.js) executed automatic guidance
after a user-triggered simulation for Cecid and Fruit Fly with CA and Tree Graph,
saved-result reuse, failure fallback, a 390-pixel layout, orchard switching and
logout during an outstanding read. They assert the expected simulation/logout
requests and no additional farm-record writes. Desktop and narrow screenshots
were visually inspected. Browser artifacts remain in
`outputs/ai-guidance-browser-20261029-reviewed/`.

## Limits and data handling

Google responses are isolated HTTP fixtures in backend checks; browser forecasts
and guidance are isolated route fixtures. These are automated software checks,
not measured forecast accuracy, field validation or a manual farm rehearsal.
The manual workflow results and bug log were left unchanged.

At the initial implementation check, no Gemini key was configured locally, so
actual Google authentication, model availability, quotas, billing, response
latency and generated-text quality had not been tested. A subsequent connection
check is recorded below. No credentials were added to tracked files or frontend
configuration.

Guidance is stored inside the existing simulation response JSON and follows the
existing cloud-sync path. No local or hosted database schema changed; the Supabase
schema apply command was unnecessary and was not run. The feature changes no
orchard, observation, treatment, alert or account records, and triggers no
notifications. Existing simulation alert behavior is retained.

The provider supplies explanations of the existing plan. Action titles, targets,
priorities, timing and steps stay rule-based; structural validation cannot establish
the factual correctness of arbitrary generated prose. The UI labels AI text and
keeps field confirmation and representative-run interpretation visible. Older
saved runs retain their original outputs and model metadata.

## Subsequent live connection check

On 29 October 2026, after the key was saved, a fresh backend process loaded a
nonempty `GEMINI_API_KEY` and enabled AI recommendations. One small request through
the application's `request_explanation` function succeeded against Google's
`gemini-3.5-flash-lite` model in approximately 8.0 seconds. The returned JSON passed
the application's structured-response and action-reference checks for one routine
scouting action.

The request used diagnostic guidance with no orchard records or forecast results.
It submitted no simulation and wrote no farm records. The key and provider text
were not printed or copied into evidence. This confirms authentication and model
access for that request; it does not establish response quality across real
forecasts, future availability, or account-wide quota/billing limits. An already
running FastAPI process must be restarted to load the saved environment change.
