# MangoPoint entire-workflow bug-testing checklist

This is a manual test plan for model `2026.10-source-progression-v17`. The cases
below have **not been executed by preparing this checklist**. Automated tests
are separate evidence; they do not establish that these browser workflows pass.

Use two passes: first complete the ordinary workflow, then try invalid inputs,
switching, interruption, and recovery. Mark each case **Pass, Fail, Blocked, N/A,
or Not run** in the [test-results sheet](manual-workflow-test-results.csv).
Use the [bug-log template](manual-workflow-bug-log.csv) for reproducible failures.

## Preparation

Use a test account and a clearly named test orchard/copy for saved tree edits,
observations, alert actions, uploads, and account changes. Keep test observations
labelled as test records. Use a test mailbox for recovery and notification checks.

Record the application/model version, browser, device, date, orchard ID, tree
count, and API/frontend startup method. Keep one other orchard available to test
switching. For biological checks, choose a source and an eligible target within
5–10 m; an isolated source may legitimately expose no targets.

Begin with 12 or 24 hours to make the first run easy to inspect, then test the
48-hour defense scenario. Record the generated seed. **Use as Template** can
restore a saved fixed seed. Equal seeds do not require the two engines to produce
equal results; compare repeated runs within the same engine and model version.

Open the browser console with F12 when investigating an error. Capture the
visible message and relevant failed request, without credentials or access tokens.

## Pass 1: ordinary workflow

Login → choose orchard → inspect/edit inputs → set weather → select pest/model
→ run → inspect results/playback → reopen from History → export → Verify → logout.

Run that sequence for these four combinations, keeping a separate record for each:

Duplicate a results-sheet row for each applicable pest/engine combination and
fill in its Run combination, Pest and Engine columns. Mark a shared workflow
case Pass only after all applicable combinations have passed. The CSV opens in
Excel; every starting status is Not run.

| Run | Pest | Host stage | Engine |
|---|---|---|---|
| A | Fruit-attacking Cecid | Fruitlet | Grid (CA) |
| B | Fruit-attacking Cecid | Fruitlet | Tree Graph |
| C | Oriental Fruit Fly | Green mature / ripening | Grid (CA) |
| D | Oriental Fruit Fly | Green mature / ripening | Tree Graph |

Start with custom weather for reproducibility. For Cecid, use moist soil at Hour
0, dry weather, light wind around 1 m/s, and an explicitly dim daytime condition
or solar dawn/dusk. For Fruit Fly, use mature targets, daytime, and about 28 °C.
Supply a known initial source scenario rather than relying on an unexplained
fallback. Inspect the saved source list after running.

## Access and navigation

| ID | Action | Expected result |
|---|---|---|
| WF-01 | Sign in with valid test credentials. | Dashboard loads without a blank screen or endless spinner. |
| WF-02 | Enter a wrong password and submit empty required fields. | A clear error or field validation appears; the dashboard is not opened. |
| WF-03 | Refresh while signed in, then visit the dashboard while signed out. | A valid session restores; signed-out access returns to Login. |
| WF-04 | Open each dashboard tab and Setup, Simulate, Results, and Verify. Collapse and reopen the workspace. | The correct panel opens; inputs and results remain coherent. |
| WF-05 | Log out, use the browser Back button, then sign in again. | Protected content requires a valid session; the app can be used again. |

## Orchard loading and input editing

| ID | Action | Expected result |
|---|---|---|
| WF-06 | Select an orchard and inspect its name, boundaries, tree IDs/count, map and orthophoto. | All belong to the selected orchard; overlays align and loading completes. |
| WF-07 | Switch orchard A → B → A, including after a completed simulation. | Tree edits, weather context, observations, alerts and displayed results are associated with the appropriate orchard; stale A results are not presented as B results. |
| WF-08 | Refresh the orchard list and reload the page. | The selected available orchard loads consistently; there is no duplicate orchard entry. |
| WF-09 | Change the saved orchard monitoring stage. | The saved stage and live screening context update; this is distinguishable from temporary simulation-stage edits. |
| WF-10 | Upload a test orchard with a name, tree GeoJSON and orthophoto GeoTIFF; include DTM/DSM if available. | Upload completes; the new orchard can be selected and its geometry/images are usable. |
| WF-11 | Try uploading with missing required files, malformed GeoJSON or an unsupported file. | Validation/error feedback appears; no partial orchard is presented as a successful upload. |
| WF-12 | Select a tree and apply Healthy, Infected, Bagged, Dead, History Infected and Suspect in turn. | The selected tree, status and legend update correctly; other trees are not unintentionally changed. |
| WF-13 | Set History/Suspect source presence to 0%, 50% and 100%; try an individual override and returning to defaults. | The intended value is retained; 0% and 100% work; the saved run records the source basis and probability. |
| WF-14 | Change a source-bearing status to Healthy or Dead. | An old source-probability override does not silently make that tree an active source. |
| WF-15 | Draw/apply stage and status zones, including overlap; cancel an unfinished polygon. | Selected IDs/counts match the polygon; overlap follows the documented precedence; cancel changes nothing. |
| WF-16 | Compare Scenario only with Apply to orchard; reload after saving an orchard edit. | Temporary edits remain identifiable as scenario edits; saved orchard edits persist and show saving/success/error feedback. |
| WF-17 | Add management and Cecid habitat/weed zones; remove one, undo where offered, and cancel a clear-all confirmation. | The intended zone changes; overlays and inventory agree; cancelling does not delete zones. |
| WF-18 | Inspect the map at the first and last simulation frames and compare with input statuses. | Simulated infestation is not silently written back as an observed orchard status. |

## Weather setup

| ID | Action | Expected result |
|---|---|---|
| WF-19 | Select Live Forecast; inspect coordinates, dates, units and source label. | Weather belongs to the orchard and exposes its source/fallback; missing cloud/radiation is not labelled zero or fabricated. |
| WF-20 | Switch Live Forecast → Custom weather → Live Forecast. | The active mode is clear; the next request uses the selected mode rather than stale values. |
| WF-21 | Set custom temperature, wind speed/direction, rainfall, duration and local start time, including zero rainfall/wind. | Entered values and Philippine-time dates survive the request, playback and saved result; wind direction means wind-from. |
| WF-22 | Build several weather periods; test an overlap and an uncovered hour. | Period boundaries are correct; later-period precedence and uncovered-hour defaults are disclosed. |
| WF-23 | Compare bright sunshine, intermittent sun and dim/overcast daylight, with observed/assumed basis. | The exact choice and basis are saved; cloud percentage alone or tree shade does not guarantee dim outdoor light. |
| WF-24 | Compare dry soil, moist at Hour 0 and recently wet context for Cecid. | Soil state/context is retained; moist at Hour 0 does not manufacture antecedent rainfall. |
| WF-25 | Change custom settings, load a saved template, and inspect every period and soil/light field. | Saved inputs replace the relevant current controls; stale editor settings do not contaminate the replay. |

## Running simulations

| ID | Action | Expected result |
|---|---|---|
| WF-26 | Complete runs A–D from the four-combination table. | Each run identifies the correct pest, engine, stage, source scenario, weather, duration and model version. |
| WF-27 | Run short, 48-hour and maximum-duration scenarios offered by the UI. | The supported duration is honored; times and frame labels are coherent. Record elapsed time instead of assuming a speed target. |
| WF-28 | Click Run Simulation repeatedly while a run is pending. | Running feedback is visible; repeated clicks do not submit accidental duplicate runs. |
| WF-29 | Switch pest/engine after a result, then run again. | New inputs produce a new correctly labelled result; the previous pest/engine is not mixed into it. |
| WF-30 | Compare observation-seeded and non-observation-seeded runs using labelled test records. | Only intended orchard/pest/date-range observations affect source setup; source provenance explains their use. |
| WF-31 | Run with outside pressure disabled, then add north/east/opposing neighbor sources and remove them again. | Each direction/level survives saving; removing all neighbors disables outside pressure; Cecid displays its exposure-proxy limitation. |
| WF-32 | Compare untreated, protective, sanitation and combined treatment scenarios with the same seed. | Correct targets and source/incoming factors are saved; recommendations do not silently become observed treatment records. |

## Results, playback and consistency

| ID | Action | Expected result |
|---|---|---|
| WF-33 | Inspect source/reservoir badges, tree details and map legends. | Badges describe initial source scenarios; new infestation is not automatically labelled an adult source; cells and trees are distinguished where relevant. |
| WF-34 | Run one realization, then 5 or 9 repeated runs. Toggle Across runs and One run. | Frequency is labelled as repeated-run frequency; one-run totals and playback remain representative outcomes. |
| WF-35 | Compare the map, Overview, spread/weather charts and Results at the same point in the run. | Figures refer to their stated frame/final result and units; unexplained contradictory totals are logged. |
| WF-36 | Play, pause, step backward/forward, drag the slider and restart at the end. | Hour, weather, map state and counts agree; playback stops at the last frame and does not run past it. |
| WF-37 | Inspect Dead, Bagged and out-of-stage trees. | Dead trees are excluded from new infestation; bagging reduces modeled pressure; unsuitable targets do not receive that pest's establishment outcome. |
| WF-38 | Change crop-impact assumptions and compare displayed calculations/report values. | Units and arithmetic agree; estimated loss/savings are labelled as scenario estimates rather than measured benefits. |

## History, reproducibility and exports

| ID | Action | Expected result |
|---|---|---|
| WF-39 | Find the completed run in History; refresh and revisit after signing in again. | The run is retained in the available storage path; browser-cache fallback is clearly identified if server storage is unavailable. |
| WF-40 | Filter History by orchard and run date/month; change grouping and export the filtered history. | Displayed/exported entries match the chosen filters and scope; execution date is not confused with custom forecast start date. |
| WF-41 | Choose Load Result while current controls/map belong to another setup. | The original saved output, orchard, metadata and frames load; this action does not create a new simulation. |
| WF-42 | Choose Use as Template, inspect restored inputs, and rerun without New random seed. | For the same model version and exact saved inputs/weather, outputs reproduce. Loading controls alone does not start a run. |
| WF-43 | Open a v16 result/template if available. | Stored results retain v16 identification; a newly executed v17 run is identified as v17 and is not promised to reproduce the old engine. |
| WF-44 | Export Excel for one run and Export History for several runs; open both files. | Files open, identify the correct run/orchard/model, and contain consistent values and weather/seed metadata where supplied. |
| WF-45 | Print a final-result report while playback displays an earlier hour; also choose displayed-hour reporting. | The default report uses final results; displayed-hour reporting uses its selected frame/map/weather and labels that hour. |
| WF-46 | Add report notes/name, export portrait PDF, cancel once, then retry. | Map/orthophoto, text, legend and saved model assumptions are legible; notes do not break layout; cancelling permits retry. |

## Field verification, alerts and account settings

| ID | Action | Expected result |
|---|---|---|
| WF-47 | Select a tree and choose Log field verification; inspect Verify. | Orchard/tree/pest and optional forecast/run link are correct; recording an observation does not fabricate a forecast result. |
| WF-48 | Save labelled test observations for Present, Absent and Not inspected; inspect their history. | Date, method, observer, counts and notes persist correctly; Not inspected is not interpreted as pest absence. |
| WF-49 | Enter affected count greater than inspected count, invalid counts or missing required fields. | Validation prevents invalid observations from being reported as successfully saved. |
| WF-50 | Open an orchard's forecast alert and apply its suggested simulation setup. | The correct orchard and scenario are prepared; screening is labelled screening and no simulation starts automatically. |
| WF-51 | Acknowledge and resolve a test alert, then refresh and switch orchards. | The intended alert's status persists; unrelated orchard alerts are not changed. |
| WF-52 | Edit the test account's profile, test password mismatch/current-password errors, and test recovery using its mailbox. | Validation and success/error messages are clear; successful changes persist; invalid or reused reset credentials are rejected. |
| WF-53 | Exercise cloud sync in the configured test environment, then refresh History. | Success/failure feedback reflects the actual sync; runs are not duplicated or assigned the wrong orchard. Mark Blocked if the service cannot be tested. |

## Pass 2: biological behavior checks

Keep inputs explicit, inspect gate/exposure diagnostics, and use both engines.
A favorable scenario can legitimately have zero **new establishments** in one
stochastic draw; eligibility/exposure and stochastic establishment are different.
For treatment/bagging comparisons, use repeated runs or the controlled scripts;
one random outcome does not prove a rate difference.

| ID | Action | Expected result |
|---|---|---|
| WF-54 | Cecid: use moist soil, fruitlets, a nearby target and a favorable dry dim-day/twilight window. | Local emergence and exposure are possible during eligible hours; sources and assumed laying/lifespan settings are identifiable. |
| WF-55 | Cecid: schedule 4 hours of heavier rain, then 1 dry favorable hour, then rain and another favorable break. | Suitable breaks can permit emergence/movement; heavier rain pauses activity; surviving adults do not disappear merely because rain resumes. |
| WF-56 | Cecid: compare bright versus explicitly dim daylight, darkness, and unsuitable host stage. | Bright/dark/unsuitable conditions close the applicable activity or host gate; cloud cover or canopy shade alone does not override it. |
| WF-57 | Run the explicit zero-source setup below for both pests and engines. | Active local sources and outside pressure are zero; no new infestation is generated. Do not use a fallback-source scenario as this test. |
| WF-58 | Fruit Fly: use mature fruit and compare daytime with reduced dark-period activity. | The model allows reduced assumed dark activity; it is not an exclusive twilight model, and unsuitable fruitlet targets remain excluded. |
| WF-59 | Fruit Fly: inspect a source–target–remote-target chain with no independent source at the middle/remote tree. | New infestation does not create outgoing adult pressure. The automated source-progression regression is the precise check if UI geometry makes the chain ambiguous. |
| WF-60 | Compare source-presence endpoints and bagged/treated targets under matched inputs. | Source assumptions affect eligibility/pressure; zero source probability stays absent. Protection modifies risk without promising immunity. |

**Explicit zero-source setup:** Use a fresh test orchard with no infected trees,
manual/soil sources or usable observation seeds. Set one tree to History Infected
with source presence explicitly at 0%, and disable all outside neighbors. This
declares an inactive source hypothesis instead of triggering the no-evidence
fallback. Check that the saved active-source count/list is actually zero before
assessing spread. Clearing all records to Healthy alone may cause assumed
fallback sources and is not a zero-source test.

The exact engine source-progression check is already available:

```powershell
python -m pytest -q tests/test_source_progression_review.py
```

## Pass 2: interruption, layout and recovery

| ID | Action | Expected result |
|---|---|---|
| WF-61 | Interrupt API access during a test run or save, restore it and retry. | An actionable failure appears, no false success is shown, loading ends, and retry works without silently losing or duplicating records. |
| WF-62 | Interrupt live-weather/map-tile access and try history loading from saved browser data. | Unavailable/fallback states are explicit; the app does not claim a complete offline live-weather/basemap capability. |
| WF-63 | Switch orchards quickly while weather/history loads; navigate between tabs while a simulation completes. | Late responses cannot replace the active orchard's inputs/results with another orchard's data. |
| WF-64 | Refresh while edits are unsaved or a run is pending; then check History. | Unsaved work is not falsely presented as saved; completed records and failures are identifiable; retry does not silently duplicate them. |
| WF-65 | Resize to a narrow window, use keyboard navigation and open/close upload, weather, settings and report dialogs. | Controls remain reachable; focus, scrolling and Escape/close behavior work; no trapped or hidden Run/Export button. |
| WF-66 | Repeat a run → result → history → report cycle several times. | No accumulating duplicate UI entries, frozen playback, stuck loading state, or steadily worsening interaction. |

## Recording and fixing bugs

For a failure, record the case ID, exact actions, expected and actual behavior,
model version, orchard/tree IDs, pest/engine, run ID/seed, weather source and
schedule, screenshot/error text, and whether repeating it reproduces the issue.
Use Actual result to explain Blocked/N/A cases as well as failures; record Pass
only after performing the check.

Example format, not an observed bug:

```text
Case: WF-41
Steps: Complete a run in orchard A; switch to B; load A's saved result.
Expected: The saved result is associated with A throughout the dashboard.
Actual: [Describe exactly what happened.]
Evidence: [Run ID, seed, screenshot, and relevant error if any.]
```

Classify **Critical** for crashes, incorrect orchard assignment, lost/corrupted
saved data, or a report that materially misrepresents results. Use **Major** for
a required workflow that fails; **Minor** for a visual issue that does not alter
the result or prevent completion. Keep a failing case open until a fix is
retested, including its adjacent workflow (for example history fix → reopen →
template → export).

If a model/input rule changes, identify the affected automated checks and
controlled/historical results before updating paper tables. Record browser
usability testing separately from biological or field validation.

## Completion check

- All four ordinary run combinations complete through results, saved history
  and exports, with their version and inputs traceable.
- No unresolved Critical or Major defects in required defense workflows.
- Remaining Minor, Blocked or N/A cases have a reason; none is counted as Pass.
- A 48-hour demo scenario and its saved report/recorded fallback are ready.
- The paper, slides and demonstration describe the same model and evidence.

This checklist supplements the [defense readiness plan](final-defense-readiness-plan.md)
and [v17 model review](v17-model-readiness-review.md).
