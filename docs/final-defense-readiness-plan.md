# Final-defense readiness plan

Item 1 was completed in the [v17 model review](v17-model-readiness-review.md).
The next work is an end-to-end demonstration rehearsal.
Paper drafting can proceed alongside this work. Final results tables
should be tied to the model version selected after the review.

The defense date and the state of the manuscript are not yet recorded here, so
this is an order of work rather than a dated schedule.

## 1. Resolve the model review findings

**Completed for v17:** Source progression was separated from new fruit damage,
graph reach was corrected, and outside-Cecid proxy/output assumptions were made
explicit. The findings below describe the review's starting point.

Review both the cellular automata and tree-to-tree graph implementations.

- **Fruit Fly source progression:** Newly affected trees currently become
  outgoing sources within the same forecast. The broad historical audit found
  that the artificial-grid Fruit Fly runs affected every target. Establish what
  an initial adult source and a newly affected target represent, and resolve
  same-forecast source propagation before interpreting spread sensitivity.
- **Outside fruit-attacking Cecid arrivals:** Outside pressure currently acts as
  a broad exposure proxy. Review what the interface promises about entry and
  movement, and ensure it matches the implemented representation. The existing
  historical evaluations excluded outside pressure and cannot validate it.
- **Output explanations:** Check the labels for affected-tree frequency,
  composite risk, pest states, weather provenance, and assumed parameters. A
  monthly fruit-damage percentage or trap-catch value is a different outcome
  from a 48-hour simulated affected-tree frequency.

Use available research and expert feedback to justify changes. Do not select
coefficients merely to increase agreement with BPI categories. Keep unresolved
assumptions explicit in the system explanation and paper.

**Completion evidence:** A short list of findings, their resolutions, the final
interpretation of each output, and focused regression checks for changed rules.

## 2. Rehearse the complete system workflow

Use the [66-case manual workflow checklist](manual-workflow-test-plan.md),
[results sheet](manual-workflow-test-results.csv) and
[bug log](manual-workflow-bug-log.csv) to record actual behavior. Preparing these
templates does not mean the workflows have been tested.

Use the actual application to demonstrate:

1. Start the application and sign in through the supported workflow.
2. Load a partner orchard and inspect or edit the relevant tree/source inputs.
3. Select each pest and engine, and configure weather and host stage.
4. Run the simulation and explain the map, hourly playback, legend, and results.
5. Confirm the run appears in History, reopen it, and verify its recorded inputs and model version.
6. Produce the supported report/export and compare it with the displayed run.

Include representative favorable conditions, a rain-break scenario, and a
no-source scenario. Record actual behavior and fix defects that interrupt or
misrepresent these workflows. Run the relevant backend/frontend checks and
production build after changes.

**Completion evidence:** A completed rehearsal checklist, reproducible demo
inputs, and any remaining limitations that the presenter must explain.

## 3. Freeze the version and refresh its evidence

After model changes, rerun the affected controlled scenarios and the historical
evaluations for both engines. Preserve earlier results for comparison. Export
the final inputs, configuration, model version, result tables, figures, and test
logs together so the paper and demonstration refer to the same implementation.

Keep the broader historical audit alongside the selected 20-case defense
replay. Report the training/test split, simple baselines, outbreak misses,
numeric errors, and limitations. The selected replay's 90% overall and 100%
2025 category agreement are version-specific results; they are not established
field accuracy. The simple baselines also matched all five selected 2025 cases.

The current v17 review records 797 passing Python cases, 143 passing frontend
cases, a successful production build and 3,000 controlled sensitivity
realizations. The selected replay's 4,800 realizations remain v16 evidence;
the BPI evaluations have not yet been rerun for v17. These counts describe
different activities and must not be added together as a single accuracy
sample. They remain evidence for the versions actually tested.

**Completion evidence:** One identified release version with matching system
outputs, evaluation exports, figures, and paper tables. Make later changes only
with an explicit assessment of which checks and results must be refreshed.

## 4. Write the paper in parallel

Follow the institution's required structure and approved objectives. If using
the usual five-chapter format:

| Paper section | Work that can begin now | Work that depends on the final version |
|---|---|---|
| Chapters 1–2 | Problem, objectives, scope, related studies, and research gaps | Check that claims and objectives match the delivered scope. |
| Chapter 3 | Architecture, both engines, data sources, model assumptions, automated testing, controlled experiments, and historical comparison methods | Update any rules or evaluation procedures changed during the review. |
| Chapter 4 | Prepare the table/figure structure and explain how to read the metrics. | Insert final results, baselines, failures, screenshots, and any actual expert/usability findings. |
| Chapter 5 | Draft the intended use, resource constraints, and future evaluation plan. | Draw conclusions only from the final evidence. |

Separate implementation verification, sensitivity analysis, historical
comparison, and user/expert evaluation. Partner interest supports relevance;
it does not establish reduced crop loss or forecast accuracy. Explain why
prospective field validation is deferred and what data a later pilot needs.

**Completion evidence:** A manuscript whose features, methods, numbers, figures,
and conclusions can be traced to the final system and saved evidence.

## 5. Prepare the presentation and supporting material

- Obtain expert review and partner usability feedback if reviewers are
  available. Record what was actually reviewed and avoid inventing findings.
- Prepare slides, a timed demo script, and answers about biological assumptions,
  both engines, BPI comparison, baselines, tests, and the lack of field validation.
- Save clearly labelled screenshots, exported results, and a recorded run for
  use if live internet/weather access interrupts the demonstration.
- Assemble the setup/run instructions, evaluation commands, final report
  artifacts, and any required user documentation.

**Completion evidence:** A timed rehearsal and a final cross-check between the
application, manuscript, slides, and evaluation artifacts.

## Existing material to use

- [Testing methods and example commands](testing-methods-for-defense.md).
- [Defense presentation guide](validation-defense-presentation-guide.md).
- [Selected historical replay and limitations](v16-validation-defense.md).
- [Broader sensitivity and BPI audit](v16-sensitivity-and-bpi-validation.md).
- [Saved Python test evidence](testing-evidence-summary.json).

The immediate task is item 2. Draft Chapter 3 alongside it; finalize Chapter 4
after item 3.
