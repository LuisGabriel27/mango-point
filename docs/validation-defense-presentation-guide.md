# Presenting MangoPoint's validation evidence

Version note: The BPI results in this guide belong to v16. The
[v17 model review](v17-model-readiness-review.md) passed 797 Python and 143
frontend cases and refreshed controlled scenarios. Its BPI comparison is pending;
do not present earlier percentages as v17 results.

This guide accompanies the [updated historical defense](v16-validation-defense.md)
and the [broader sensitivity/BPI audit](v16-sensitivity-and-bpi-validation.md).
It does not change the model or the validation results.

For commands, examples of actual checks, and an explanation of the run counts,
see [how the tests and controlled runs were performed](testing-methods-for-defense.md).

## The claim supported by the work

MangoPoint is a working prototype for organizing orchard information and
exploring pest-risk scenarios. Its implementation has undergone software tests,
controlled simulation experiments, and a retrospective comparison with BPI
monthly records. Forecast accuracy at individual trees, infestation reduction,
and economic benefits remain unestablished.

Keep this claim aligned with the study's approved objectives. If an objective
requires demonstrated predictive accuracy in partner farms, identify that part
as incomplete. Resource constraints explain the study's coverage; they do not
establish the missing field result. Agreement on an evaluation scope ultimately
rests with the adviser and panel.

Simulation research recognizes software verification, expert assessment,
historical comparisons, and sensitivity analysis as complementary methods.
Their findings must be judged against the particular intended use. Sargent also
distinguishes predictive validation, where forecasts are compared with later
real-system observations. This supports using multiple evaluation methods while
keeping each claim within the evidence obtained.
[Sargent, 2011, Verification and Validation of Simulation Models](https://informs-sim.org/wsc11papers/016.pdf).

## Evidence to present

| Evidence | Current result or source | What it supports |
|---|---|---|
| Software verification | 785 passing Python tests | The behavior covered by those tests operates as specified. This does not measure infestation forecast accuracy. |
| Biological basis | Research references and the pest-expert feedback already obtained | A rationale for fruit-attacking Cecid and Fruit Fly rules. Record which rules the expert reviewed; several quantitative parameters remain assumptions. |
| Controlled experiments | 3,000 realizations across 50 scenarios and two engines | How the implemented models respond to changed inputs and assumptions; which parameters materially affect outputs. |
| Selected historical comparison | Each engine matches 18/20 classes after training-only calibration | Retrospective class agreement in the documented 20-case design. |
| Broader historical audit | All 46 recorded months retained per pest, with baselines | Coverage beyond the original calendar and evidence of important forecast limitations. |
| Partner-farm interest | The interest reported by the team | Relevance and anticipated usefulness. Document it with dated interviews or letters. |
| Prospective field validation | Not completed within available resources | Individual-tree forecasting skill and farm outcomes remain open questions. |

The tests and repeated simulations are not new independent field observations.
The 4,800 defense realizations still compare with only 20 observed pest-month
cases per engine. CA and Tree Graph use the same BPI observations, so their
agreement is not two independent datasets confirming accuracy.

## Present the historical percentages with their context

For both current engines:

- Cecid: 8/8 selected monthly classes match, comprising six Low and two Medium
  observations. No High Cecid observation appears in this selected subset.
- Managed Fruit Fly: 10/12 classes match. Two of four High observations are
  classified as Medium, giving 50% High-category recall.
- Combined: 18/20 matches, or 90%; this includes the calibration cases.
- Held-out 2025: 5/5 matches, comprising two Low Cecid and three Medium Fruit Fly
  cases. A training-majority prediction also matches all five.

State that numeric mappings and class cut-points were fitted on 2022–2024 and
frozen before application to 2025. Previous-month observed BPI pressure remains
an input, including earlier observations in the test year. The score combines
simulation, weather suitability, and observed carryover; 90% is the agreement
of that calibrated historical setup.

Include the broader audit in the presentation or discussion. Its all-month
Cecid predictions miss the five Medium/High observations, and Grid Fruit Fly
affected frequency saturates at 1.0. In the selected defense replay, all 12 Grid
Fruit Fly spatial scores are also 1.0. These are substantive model limitations.
The historical archive also lacks the light fields needed to evaluate the new
cloudy-daylight allowance.

## Four-slide presentation sequence

1. **Problem and delivered prototype.** Describe the partner farms' monitoring
   needs and demonstrate the orchard map, weather inputs, observations, scenario
   controls, and reports. Explain the task each feature supports. Keep expected
   benefits separate from measured outcomes.
2. **Evaluation methods.** Show the relevant software checks, documented expert
   feedback, and controlled scenario experiments. Use one traceable example to
   connect an input change with the model's response. Mark assumed inputs.
3. **Historical findings.** Show the historical weather replay, calibration/test
   split, both engine results, baseline comparison, and missed outbreak cases.
   Include the broader audit's limitations. Use case counts beside percentages.
4. **Study boundaries and next evaluation.** Explain resource constraints,
   unresolved model issues, and a staged partner-farm evaluation. Distinguish
   usability testing from testing forecasts against later pest observations.

## Suggested speaking script

“Within our available resources, we evaluated MangoPoint through software
verification, controlled simulation experiments, and historical comparison with
BPI records using weather from the corresponding months. Both engines matched
18 of 20 selected monthly risk classes after calibration on 2022–2024 records.
They matched all five selected 2025 classes, although a simple baseline also
matched those cases. The broader evaluation identified limitations in outbreak
detection and Fruit Fly spread behavior. Our findings demonstrate an implemented
and tested prototype and limited historical class agreement. Individual-tree
forecast accuracy and farm-level benefits require further evaluation. Partner
farms' interest supports the relevance of continuing that work.”

## Responses to likely panel questions

**Does 90% mean the system predicts infestation accurately?**

“It means 18 of 20 selected monthly classes matched under the calibrated
historical design. The observations are monthly aggregates, and the score uses
weather and previous-month pest pressure. It does not establish the accuracy of
a prediction at an individual tree.”

**Why is field validation absent?**

“Our resources did not permit prospective, dated tree inspections covering the
forecast period. We report that limitation and the evaluations we completed.
Those methods provide partial evidence; prospective forecast evaluation remains
necessary.” State the team's actual constraints and avoid inventing specific
budget, season, travel, or access problems.

**How can farms benefit before forecast accuracy is established?**

“They can evaluate the prototype's usefulness for viewing orchard information,
reviewing weather, recording observations, and exploring explicitly assumed
scenarios. We propose measuring those tasks and addressing known model issues
before relying on forecast performance for farm decisions.”

**Do interested partner farms validate the model?**

“Their interest documents a practical need and willingness to participate.
Usability, forecast accuracy, and reduced crop losses require their own measured
evidence.”

## Useful work possible within tighter resources

- Obtain a dated expert review of the actual rules, assumed coefficients, and
  known limitations. Expert feedback on behavior should not be described as
  endorsement of every prediction or coefficient.
- Ask farm representatives to perform concrete prototype tasks, remotely if
  appropriate: find a tree, enter an observation, interpret an assumed scenario,
  and retrieve a report. Record completion, errors, time, and feedback. Label
  this usability evaluation; do not count it as field forecast validation.
- Record partner-farm needs and interest through documented interviews or
  letters. Keep exact participant counts and statements traceable.
- Prepare a future observation protocol: save dated predictions before later
  inspections; retain tree IDs, pest identification, weather, stage, treatment,
  and source evidence; inspect across predicted risk levels; compare missed
  infestations and false alarms against simple baselines. Plan the sample size
  and acceptable performance with the adviser and pest expert.

Farm monitoring features can be evaluated separately from model accuracy. FAO
describes digital pest tools as helping organize observations, improve
traceability, and connect information with decisions, alongside field expertise.
That is a relevant direction for a partner-farm pilot, rather than evidence that
MangoPoint already delivers those benefits.
[FAO, 2026, From field observations to early warning](https://www.fao.org/transboundary-plant-pests-diseases/news/detail/from-field-observations-to-early-warning--improving-pest-surveillance-for-faster-response/en).
