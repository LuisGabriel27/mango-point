# Model readiness review: v17

Review date: 10 October 2026. Model: `2026.10-source-progression-v17`.

This completes item 1 of the [final-defense readiness plan](final-defense-readiness-plan.md):
review and resolve source progression, outside Cecid representation, and output
explanations. It does not complete the application rehearsal or establish field
accuracy. The earlier BPI percentages remain results of their tested v16 version.

## Findings and resolutions

| Finding | Resolution |
|---|---|
| Newly infested Fruit Fly targets became outgoing sources during the same forecast. | Both engines now capture initial adult-source pressure separately from fruit infestation. New infestation does not add a source. |
| A historical Fruit Fly reservoir could be promoted to full source pressure when its fruit became infested. | Its initial pressure remains unchanged by the damage transition. Treatment source factors still apply. |
| Graph spatial reach counted a whole connected component as reachable from an initial Fruit Fly source. | Report direct source-linked exposure separately from the component topology; newly affected trees do not extend this reach. |
| Recorded fruit damage could be read as verified adult presence. | Explain that the record supplies an initial source scenario; fruit damage does not measure adult presence. |
| Outside Cecid pressure could be mistaken for a tracked boundary-arrival path. | Retain the directional exposure proxy and explicitly describe its lack of boundary crossings, travel time, adult age, and egg-capacity tracking. |
| Saved runs and printable reports lacked these distinctions. | Save pest-specific model interpretations with new results and include them in reports. Older runs retain their version and are not assigned new assumptions. |
| Evaluation scripts could overwrite v16 outputs or label newer plots as v16. | Default output directories follow the current model revision. New tables and figures use the recorded revision/version. |

No spread, temperature, bagging, or laying coefficients were tuned to improve
BPI agreement. The new version identifies the changed Fruit Fly source rule.
There was no database schema change.

## Fruit Fly: how the revised rule works

At the beginning of a forecast, each engine captures the supplied initial
infestation and reservoir scenario. An initially infested source supplies full
modeled adult pressure; a separate historical reservoir retains its supplied
strength without requiring infested fruit at that location.

During each eligible hour, that initial pressure contributes exposure through
the existing grid offsets or graph edges, with weather, stage, bagging, and
treatment modifiers. A target can become infested in the simulation. That
transition updates the fruit outcome; it does not add another adult source or
increase reservoir pressure. An explicitly removed source does not emit pressure.

For example, A may expose B through a local link. If B becomes infested, it
cannot expose C merely because its fruit changed state. B can expose C if B
already had independent adult-source/reservoir pressure in the initial scenario.

This prevents simulated fruit infestation from behaving as immediate adult
reproduction. Experimental work on *Bactrocera dorsalis* reports separate egg,
larval, and pupal development over days. The study's reported stage means
support rejecting immediate egg-to-adult conversion; they do not calibrate this
project's spatial coefficients. [Dongmo et al., temperature-based phenology study](https://pubmed.ncbi.nlm.nih.gov/33863442/).

**Remaining approximation:** Initial pressure stays anchored at its source
locations. Existing adults can expose targets within the local links, but the
model does not relocate individual adults across successive links, simulate
immature development, or infer a measured adult population from damaged fruit.
The link distances are model choices, not biological maximum flight distances.
Movement of existing adults must be modeled separately if that becomes a
requirement; it must not be inferred from new fruit damage.

## Fruit-attacking Cecid: outside exposure and local cohorts

The local model continues to use soil-source cohorts, suitable emergence and
movement windows, habitat relays, adult aging, and normalized laying capacity.
New fruit infestation does not generate a new local soil source in the
application's cohort-based forecast. Tree shade alone does not open activity.

The fruit-attacking scope is retained. The UPLB field/laboratory abstract reports
soil pupation and distinguishes the fruit-attacking midge from leaf midges. It
does not establish the project's exact lifespan, movement, or laying settings.
[Medina, Pamiloza and Velasco, bioecology study](https://www.ukdr.uplb.edu.ph/journal-articles/4814/).

Outside pressure is a separate exposure estimate, conditional on suitable
fruitlets, light, rain, and wind. A positive directional projection can expose a
remote tree in the first eligible hour. It does not establish that an adult
crossed the boundary and traveled to that tree. The local 15 m movement cap and
cohort age/laying diagnostics do not constrain or describe this outside proxy.

The interface, saved metadata, and report now make that limit explicit. Map
explanations describe estimated exposure rather than claim an observed arrival.
The existing historical comparisons excluded outside pressure, so they provide
no validation of this feature. Boundary-entry cohorts remain a separate future
model change requiring source location and timing evidence.

## Output interpretation

- A newly infested tree/cell is a modeled establishment outcome, not a dated
  field inspection or a measurement of visible symptoms.
- A representative run shows one stochastic outcome. Its infested locations
  display 100% in that run; this is not an ensemble probability.
- Repeated-run infestation frequency is conditional on the supplied scenario
  and model assumptions. It is not calibrated field probability, fruit-damage
  percentage, or adult trap catches per trap per day.
- Historical composite scores additionally use weather and observed prior-month
  values. Their calibrated category agreement evaluates that comparison method,
  rather than the spatial engine alone.
- Missing live/archived light remains unknown. Custom weather and light values
  remain observations or assumptions according to their supplied provenance;
  custom settings are not inherently more accurate.

These explanations are stored as `metadata.model_interpretation` on new API
results. Printable reports use the saved explanations, with an explicit missing
record notice for older runs.

## Checks and controlled comparisons

The full Python suite passed **797 cases**. Twelve added cases cover source
progression in both engines and both scalar/mixed-stage paths, reservoir pressure,
independent grid copies, graph reach, and saved metadata. **143 frontend cases**
passed, including report persistence/escaping and older-run interpretation.
The production build passed. After versioned evaluation-export adjustments,
37 focused source/audit/replay checks, both CLI help commands, and a saved-v16
export check passed. The focused cases are included in the full suite count.

Reused the existing 50-scenario design with both engines, seeds 1000–1029,
and 48-hour runs: **3,000 new controlled realizations**. Geometry, scenario
inputs, and coefficients match the v16 design. This is a software/model
comparison, not a new field-validation sample.

Mean newly affected targets in the baseline, out of 47 evaluated target trees:

| Pest | Engine | v16 | v17 |
|---|---|---:|---:|
| Fruit-attacking Cecid | CA | 3.8333 | 3.8333 |
| Fruit-attacking Cecid | Tree Graph | 4.1667 | 4.1667 |
| Oriental Fruit Fly | CA | 46.3000 | 19.1000 |
| Oriental Fruit Fly | Tree Graph | 41.3333 | 11.0667 |

All **2,160 Cecid result rows** match v16 exactly, including lifecycle fields.
All **117 separate daylight probes** match as well. No-source Fruit Fly scenarios
still produce zero new infestation in both engines. Lower/higher source spread
settings now produce distinct outcomes under the tested baseline geometry.
These changes remove an immediate source-multiplication mechanism; they do not
prove that every possible saturation case is resolved or that forecast accuracy
improved.

Compact evidence: [v17 sensitivity summary](v17-sensitivity-summary.csv),
[paired v16/v17 comparison](v17-source-review-comparison.csv), and
[review evidence manifest](v17-source-review-evidence.json).
Full logs, raw runs, input hashes, design, probes, and figures are in
`outputs/source-review-v17/`. Earlier v16 artifacts were preserved.

Reproduction from the project root:

```powershell
python -m pytest -q --junitxml=outputs/source-review-v17/python-tests.xml
python -m scripts.run_revision_audit --part sensitivity --output outputs/source-review-v17 --seeds 30
```

From `frontend/`:

```powershell
npm.cmd test
npm.cmd run build
```

## Next steps in the defense plan

Item 2 is an end-to-end application rehearsal. Item 3 refreshes both the broad
BPI audit and selected defense replay for the version chosen after that work.
**Do not carry the previous 90%/100% BPI claims forward as v17 results.**
No new BPI evaluation or field-accuracy claim was made during this review.
