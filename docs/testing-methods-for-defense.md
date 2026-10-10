# Explaining the automated tests and controlled simulations

## How to describe the capability

“Our project includes developer testing and simulation-evaluation tools. We
use the standard Python testing framework pytest to run project-specific checks,
and Python scripts to run repeatable scenario experiments. These tools run from
the terminal and call the application's backend functions and simulation
engines.”

This describes the current implementation. The testing suite is part of the
project codebase; the reported evaluations were executed through command-line
tools. Describe them as automated testing and evaluation scripts rather than
suggesting that the dashboard has a farmer-facing automated-test feature.

Pytest is an existing framework. The project's contribution is its checks,
scenario definitions, simulation orchestration, and result exports. The entire
785-case suite includes existing and added checks; it is not 785 newly written
biological experiments.

## What the 785 passing tests mean

A typical check has three steps:

1. Supply known inputs, such as a defined rainfall schedule, light condition,
   host stage, and source configuration.
2. Call the relevant application function, service, or simulation engine.
3. Compare the result with a specified requirement using an assertion.

An assertion is a programmed check, such as “the number of newly affected
targets must equal zero.” If the result violates the requirement, pytest reports
a failed test. A pass means that the tested implementation satisfied that
requirement under those inputs.

Examples that exist in the project:

| Check | Setup | Expected result checked in code |
|---|---|---|
| Missing pest sources | No local sources and no outside pressure, in each engine and pest mode | No newly affected targets. |
| Cecid rain interruption | Four hours at 2 mm/h, then a dry hour, later more rain and another dry interval, with suitable light/hosts | Emergence during the first favorable break; activity pauses during heavier rain and resumes during the later break; the adult cohort persists. |
| Bright versus dim cloudy conditions | Defined cloud/radiation inputs with soil sources, moisture, and fruitlets | Bright conditions do not open the daytime allowance; supported dim conditions can. |
| Finite laying capacity | Consume part of a modeled cohort's laying budget, then consume the remainder | The cohort retains capacity after partial laying and is spent when the budget is exhausted. |
| Held-out calibration separation | Change 2025 outcome labels while keeping training records and simulated scores fixed | Fitted curves, class cut-points, and predictions remain unchanged. |

Some checks test small functions; others exercise engines or service workflows.
Pytest also runs the same check with several combinations of inputs. Each
combination counts as a test case. Therefore 785 means executed automated cases,
not 785 source files, distinct biological rules, or independent field samples.

The full suite is run from the `mango-point` project folder:

```powershell
python -m pytest -q
```

Examples can be inspected in:

- `tests/test_cecid_daylight.py`.
- `tests/test_fruit_pest_lifecycle.py`.
- `tests/test_revision_audit.py`.
- `tests/test_defense_replay.py`.

The recent full run was also executed with a saved machine-readable report:

```powershell
python -m pytest -q --junitxml=outputs/defense-test-evidence/python-tests.xml
```

Saved evidence:

- `outputs/defense-test-evidence/python-tests.log`: console output.
- `outputs/defense-test-evidence/python-tests.xml`: each case's name, outcome,
  and execution time.
- `outputs/defense-test-evidence/python-test-cases.csv`: the same case outcomes
  in a spreadsheet-readable table.
- `outputs/defense-test-evidence/evidence_summary.json`: recorded counts,
  Python/pytest versions, and artifact hashes.

The [retained evidence summary](testing-evidence-summary.json) records 785
passed cases, zero failures/errors/skips, Python 3.11.9, and pytest 9.0.2.
The controlled-run counts were checked against the existing experiment files;
the 3,000 simulations were not rerun to create this explanation.

JUnit XML is a standard test-result format. It is unrelated to BPI observations
and does not imply that the system was tested using Java.

## What the 3,000 controlled runs mean

These are a separate sensitivity experiment, implemented in
`validation/revision_audit.py` and launched with
`scripts/run_revision_audit.py`.

Each run simulates 48 hours in a constructed orchard with 49 tree positions,
10 m spacing, two potential source positions, and 47 evaluated targets. CA and
Tree Graph use the same tree coordinates for this experiment. External pressure
is disabled. The baseline assumes 28 °C, 2 m/s wind, approximately half of the
targets bagged, defined cloud/light inputs, and initial soil moisture for Cecid.
These are controlled scenarios, not measured conditions at the partner farms.

The script defines 50 scenarios in total: 36 Cecid and 14 Fruit Fly. These
include baselines and variations in egg/laying capacity, adult persistence,
soil moisture, movement range, light, rain interruption, source presence,
bagging, temperature, spread rate, and host stage.

Most variants change one input or parameter relative to that pest's baseline.
The rain-break scenario is a specified combination of rainfall, initial moisture,
and dim light; its result cannot be attributed to rainfall alone. Temporary
coefficient changes are restored after each experiment and are executed in a
separate process from normal application requests.

Each scenario is run in both engines with 30 reproducible random seeds:

```text
50 scenarios × 2 engines × 30 repetitions = 3,000 simulation runs
```

A random seed initializes the random-number generator. Using seeds 1000–1029
allows the runs to be reproduced. Reusing this seed list across a baseline and
its variants helps compare outcomes under repeatable stochastic conditions;
different engines do not have to produce identical results from the same seed.

The repeats help show whether an outcome is typical or varies across runs.
The script records newly affected targets, timing of first affected targets,
distance from sources, and relevant Cecid cohort diagnostics. It calculates
averages, run quantiles, and paired differences from the baseline. These
describe model variability, not confidence in real-world forecast accuracy.

An actual example from the recorded Cecid results:

| Laying-capacity setting | CA mean newly affected targets | Tree Graph mean newly affected targets |
|---|---:|---:|
| Smaller setting | 2.30 | 1.90 |
| Default setting | 3.83 | 4.17 |
| Larger setting | 6.30 | 6.50 |

Each entry averages 30 runs, so fractional tree counts are expected. The input
is a normalized laying-capacity setting, not a directly measured count of eggs.
The experiment shows sensitivity to that assumption; it does not establish the
correct biological capacity in a farm.

The original output files are:

- `outputs/revision-v16-audit/sensitivity_runs.csv`: 3,000 individual results.
- `outputs/revision-v16-audit/sensitivity_summary.csv`: 100 scenario/engine
  summaries, each covering 30 runs.
- `outputs/revision-v16-audit/sensitivity_design.json`: settings and seed list.
- `docs/v16-sensitivity-summary.csv`: retained summary for review.

To repeat the experiment into a separate output folder:

```powershell
python -m scripts.run_revision_audit --part sensitivity --seeds 30 --output outputs/defense-sensitivity-demo
```

The script also exports separate deterministic light-response probes. Those
probes are not counted in the 3,000 stochastic runs.

## Keep the three evaluations separate

| Evaluation | Main question | What the count represents |
|---|---|---|
| Automated tests | Does the implementation satisfy the checked requirements? | 785 executed test cases. |
| Controlled sensitivity | How do modeled outcomes change with specified inputs/assumptions? | 3,000 repeated scenario simulations. |
| BPI defense replay | How closely do calibrated monthly classes match selected BPI observations? | 20 observed pest-month cases per engine, evaluated through 4,800 simulation realizations. |

No overall “accuracy” percentage should combine these counts. Passing
software checks and observing model sensitivity cannot establish field
prediction accuracy. The [BPI report](v16-validation-defense.md) explains
the historical comparison's calibration and baseline limitations.

## A short demonstration for the panel

Have the full test log and CSV results available. A live demonstration can run
two relevant checks quickly:

```powershell
python -m pytest -v tests/test_cecid_daylight.py::test_rain_four_hours_then_dim_one_hour_break_emerges_and_survivors_resume tests/test_revision_audit.py::test_no_sources_or_incompatible_stage_cannot_generate_audit_spread
```

This selects six test cases across the engines/pests. Explain the inputs and
expected requirement before showing the pass/fail output. Open the corresponding
test function so the panel can see the programmed check. Then open a few rows
of the controlled-run CSV and its matching summary to show recorded inputs,
seeds, and outcomes. Prepare the full 3,000-run results in advance rather than
spending presentation time rerunning the whole batch.

This six-case demonstration was run and all six passed. Its output is saved in
`outputs/defense-test-evidence/representative-tests.log` and
`outputs/defense-test-evidence/representative-tests.xml`. These cases are a subset
of the 785, not additional cases to add to that total.

## Short speaking script

“We used pytest to run automated checks against the project's implementation.
Each check supplies defined inputs and tests an expected requirement; the suite
passed 785 cases. Separately, we used a batch script calling the same simulation
engines to test 50 controlled scenarios in both models, repeating each 30 times
for a total of 3,000 runs. We saved the individual outputs, settings, and
summaries so the evaluation can be reproduced. These establish tested behavior
and sensitivity under our stated assumptions. Forecast performance against
real pest observations is assessed separately.”

## Answers to likely follow-up questions

**Who decides the expected behavior?** Requirements come from documented
software specifications, biological evidence, expert input, and explicit model
assumptions. Tests check the implementation against those requirements.
An incorrect biological assumption can still pass a software test, so expert
assessment and observation-based evaluation remain separate.

**Did you build pytest?** No. Pytest is the standard testing framework used.
The project contains its own test cases and experiment scripts.

**Can you show the test code?** Yes. The named files, commands, per-case report,
and scenario exports are available. Be ready to explain at least one assertion
and one input/output example.

**Why repeat scenarios?** Spread includes random events. Repeats expose that
variability and give a more informative comparison than a single simulation.
They do not create additional real farm observations.

**Does passing mean there are no defects?** It means the covered cases passed
in the recorded environment. Untested inputs, incorrect assumptions, and
unmeasured field behavior remain possible.
