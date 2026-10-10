# v16 sensitivity tests and BPI historical comparison

Evaluation date: 10 October 2026. Model: `2026.10-daylight-light-v16`.

This is retained v16 evidence. See the [v17 model review](v17-model-readiness-review.md)
for the revised source rule and controlled comparison. The BPI figures below
have not been rerun for v17.

The current BPI records support a monthly comparison, but the results do not
establish accurate orchard forecasts. In particular, Cecid's perfect 2025
category agreement comes from an entirely Low-category test period. Fruit Fly's
80% agreement on the mapped orchard equals a constant-category baseline. Neither
percentage should be presented as demonstrated tree-level prediction accuracy.
This audit changes no production biological coefficients or database records.

## Experiments and retained evidence

The controlled sensitivity suite uses 50 scenarios, both engines, and 30 paired
seeds per scenario: 3,000 realizations. Each orchard has 49 trees, 10 m spacing,
two candidate sources, and 47 evaluated target trees. The same coordinates are
used in Grid and Tree Graph; their different spatial probability models mean
identical seeds do not require identical results. External sources and treatments
are disabled. Baseline source presence is 100% to isolate biological response;
it is not a replacement for the application's uncertain-source default.

The baseline has 50% of target trees bagged, 70% bagging reduction, 28 °C,
2 m/s wind from the west, no rain, assumed initial soil moisture 1, 80% cloud,
GHI at half the approximate clear-sky reference, and daytime DNI 200 W/m².
Forecasts start at 08:00 Manila time on 1 April and last 48 hours. Cecid uses
fruitlet hosts; Fruit Fly uses mature hosts. Fresh local soil batches are assumed
at Hour 0, with no antecedent replay in this controlled experiment.

Ordinary coefficient variants change one setting. The rain-break control combines
4 hours of 2 mm/h rain followed by a 1-hour dry break, repeated, with dim overcast
and initially dry soil. It tests the combined scenario; its difference from the
baseline cannot be assigned solely to rainfall. Bright, intermittent, and dim
conditions are assumed scenarios, not locally observed weather.

The suite varies Cecid egg capacity, adult lifetime/pressure decay, soil moisture
decay, movement range, wind assistance, cloud/light response, source presence,
bagging, spread probability, weather pauses, and host stage. Fruit Fly tests
temperature, spread rate, night activity, source presence, bagging, and stage.
The 72-hour Cecid lifetime is an exploratory stress case outside the project's
expert-informed 48-hour default, not a newly accepted biological maximum.

An additional 117 deterministic cloud/radiation combinations probe the light
response at 50%, 65%, and 80% cloud. This matters because the main suite's 80%
cloud saturates the cloud ramp and cannot identify its lower threshold.

The CSV contains affected counts, first affected hour, distance from a source,
cohort exhaustion, mean paired changes, and standard errors. The 5th–95th
percentiles describe variability across simulated runs. They do not measure
confidence in field accuracy. First-hour statistics include only runs with
spread and use hours since the 08:00 forecast start. Distance is measured from
the closest sampled source; it is not total adult travel distance.

## Sensitivity findings

Means below count newly affected targets out of 47, after 48 hours.

| Pest / setting | Grid | Tree Graph |
| --- | ---: | ---: |
| Cecid baseline, 8 opportunity-hour capacity | 3.83 | 4.17 |
| Cecid capacity 4 | 2.30 | 1.90 |
| Cecid capacity 16 | 6.30 | 6.50 |
| Cecid source presence 50% per source | 2.33 | 2.27 |
| Cecid all evaluated target trees bagged | 2.10 | 1.67 |
| Cecid bright sunshine | 3.73 | 3.13 |
| Cecid dim overcast | 4.27 | 3.87 |
| Cecid repeated rain breaks | 2.17 | 1.70 |
| Cecid continuous 2 mm/h rain | 0.00 | 0.00 |
| Fruit Fly baseline | 46.30 | 41.33 |
| Fruit Fly source presence 50% per source | 33.83 | 27.07 |
| Fruit Fly all evaluated target trees bagged | 44.37 | 26.10 |
| Fruit Fly 22 °C | 42.93 | 24.70 |
| Fruit Fly half baseline spread rate | 43.60 | 22.63 |

Egg depletion materially changes Cecid outcomes. Changing capacity from 4 to 16
approximately triples affected counts in this orchard. The value 8 therefore
needs field calibration; it is not just an inconsequential UI setting.

Source presence and host stage remain decisive. No sampled sources or incompatible
hosts produce no new infestation in either engine for either pest. Zero initial
soil moisture with no subsequent rain prevents local Cecid emergence. Continuous
rain closes Cecid activity, while a favorable rain break permits release and
later movement by the surviving cohort, as the regression tests also verify.

Light evidence changes timing more clearly than final counts. Cecid's mean first
affected hour is 1.76 / 1.97 under dim overcast versus 12.27 / 15.30 under bright
sunshine (Grid / Tree Graph). Missing light matches bright daytime closure in
this experiment, while twilight remains available. An orchard can therefore
still accumulate damage later even when noon activity is closed. Canopy shade
is not an activity trigger.

Several weak effects are specific to this experiment. Soil half-life has no
effect once a positive moisture score has released the entire source batch.
Adult lifetime has little effect when eggs are spent first, and a 48-hour
forecast cannot adequately test a 72-hour lifespan. Cloud minimum has no effect
at a saturated 80% cover, but changes the separate 65%-cloud response. Zero
effects here do not establish that these parameters are correct or irrelevant.

Movement-range and activity changes do not always increase final counts. The
finite shared egg budget, timing, relay paths, and changed stochastic draws can
produce non-monotonic outcomes. In Tree Graph, increasing the range from 15 to
20 m gives 3.13 affected targets versus 4.17 at baseline. That scenario result
does not establish a biological benefit from reducing flight range; a larger
factorial study and measured egg deposition would be needed to resolve it.

Fruit Fly's Grid baseline affects 98.5% of target trees versus 87.9% in Tree
Graph. This makes the Grid less responsive to interventions by the final hour:
even all targets bagged still yields 44.37 / 47 affected. Present-day geometry
and the rate model strongly affect outputs. The model currently lets newly
infested Fruit Fly trees contribute outgoing spread during the same forecast;
it does not represent a measured immature-development delay. That can amplify
rapid spread and requires a separate source/lifecycle review.

## What the BPI records contain

The repository's CSV has 46 monthly records, January 2022–October 2025.
Cecid is fruit infestation percentage. Fruit Fly has separate managed and
unmanaged catch-per-trap-per-day (CPTD) series; those are adult monitoring
measurements, not fruit infestation percentages. The raw BPI source document,
fruit sample denominators, trap counts, exact inspection dates, species
identification, treatment history, and monthly orchard host-stage records are
not included in this CSV. The transcription has not been independently checked
against the original BPI sheets in this audit.

The weather archive has 35,064 hourly records for 2022–2025, without duplicate
timestamps or nonhourly gaps. It lacks cloud cover, GHI, and DNI. Missing light
stays unknown: the new Cecid daytime exception cannot be historically evaluated
with this archive, although dated solar twilight is still active. Open-Meteo's
radiation definitions distinguish instantaneous readings from preceding-hour
averages, so they should not be substituted without documenting the change.
[Open-Meteo documentation](https://open-meteo.com/en/docs).

The validation CSV loader now retains optional cloud and instantaneous light
fields when a future enriched archive supplies them. Normalized column names
take priority over API aliases. Invalid readings stay unknown and legitimate
zero readings remain zero; preceding-hour-average radiation is not substituted.
The existing archive itself has not been changed or filled with synthetic light.

Input hashes are retained in `input_audit.json`. The mapped orchard has 194 tree
points; its current crown widths and locations are not reconstructed historical
states. The artificial Grid has 20×20 tree cells at 5 m spacing. BPI observations
are not linked to individual trees in either layout.

## Historical comparison design

Both pests are tested for every available month. The old calendar filter kept
only 20 cases and excluded Cecid infestation of 48% in January 2022, 27.4% in
February 2023, and 8.15% in May 2023. Keeping only the assumed fruiting months
would hide observations the model needs to explain. The new full-month comparison
instead assumes appropriate hosts throughout; this is an explicit scenario
assumption, not a claim that the orchard really had those stages all year.

Each case samples four 48-hour windows across its month and ten stochastic
realizations per window: 7,360 historical realizations across both engines.
The unmanaged comparison reuses Fruit Fly simulations and is not counted as
additional realizations. Each window starts with 1–3 deterministic assumed
sources independent of the target month's BPI value. Cecid sources are finite
one-batch cohorts; the mapped Tree Graph includes tree relay movement. Initial
rainfall history is zero and there is no antecedent adult replay in this
monthly comparison. Consequently it is a conditional fresh-source scenario,
not an exact replay of the current live-weather workflow. External pressure,
bagging, and treatment are neutral because the historical file does not supply
their values.

The raw score is mean final affected-cell/tree frequency, including the seeded
hosts. No previous BPI value or separate weather score is blended into it.
Raw infestation frequency is not naturally equivalent to fruit-damage percentage
or CPTD. A small nonnegative affine mapping converts it to the existing
normalized comparison scale, using 2022–2024 only, then evaluates January–October
2025 with the frozen mapping. Biological coefficients stay unchanged. Class
cutoffs are not optimized against the test data.

Earlier-year checks also fit the mapping on 2022 and test 2023, then fit on
2022–2023 and test 2024. This exposes outbreak performance missing from the
all-Low 2025 Cecid period. These are retrospective splits: all those records
already existed in the project. They are not prospective unseen field trials.

Baselines are the training median, the training median for each calendar month,
the most frequent training category, and the preceding month's observation.
The preceding-month baseline is a rolling comparison and may use an earlier
2025 observation; it is not a whole-year forecast made in January.

Project comparison categories use Cecid 5% / 15% and Fruit Fly 8 / 20 CPTD.
The CSV does not establish that these are official BPI action thresholds.
Numeric proxy scores use Cecid percent/100 and the existing CPTD/40 scale for
both Fruit Fly series. Values above 40 are clipped, which loses magnitude for
some unmanaged observations. Accordingly unmanaged normalized errors must not
be described as calibrated trap-catch errors in physical units. The unmanaged
series gets a separate mapping of the same raw simulation; management differences
have not been independently simulated.

## BPI results and what they mean

The mapped Tree Graph results are:

| Series / test period | Cases | Raw category agreement | After training-only mapping | Constant majority baseline |
| --- | ---: | ---: | ---: | ---: |
| Cecid, 2025 | 10 | 100% | 100% | 100% |
| Managed Fruit Fly, 2025 | 10 | 10% | 80% | 80% |
| Unmanaged Fruit Fly, 2025 | 10 | 40% | 50% | 50% |
| Cecid, 2023 | 12 | 66.7% | 66.7% | 66.7% |
| Managed Fruit Fly, 2023 | 12 | 8.3% | 33.3% | 33.3% |
| Unmanaged Fruit Fly, 2023 | 12 | 25% | 50% | 33.3% |

All ten Cecid records in 2025 fall below 5%, including June's 4.82%. A constant
Low warning therefore receives 100% category agreement. In 2023, the mapped
model misses all four Medium/High months: outbreak-category recall is 0 / 4.
The preceding-month baseline detects three of those four and has 75% category
agreement. The 2025 Cecid score mapping has slope zero: it becomes a constant
2.90% proxy and does not demonstrate an informative biological forecast.
Its normalized test MAE is 0.0268, worse than the training-median baseline's
0.0061, despite identical 100% category agreement.

For managed Fruit Fly in 2025, the calibrated mapped model predicts Medium
each month, matching eight Medium observations and missing two Low observations.
Its normalized MAE is 0.0786 versus 0.1001 for the training median, a modest
numeric improvement in this small test period, without an improvement in
category agreement. Earlier 2023 agreement is only 33.3%. Unmanaged 2025
agreement is 50%, compared with 60% for the seasonal-median baseline.

The artificial Grid's 2025 comparison is:

| Series | Cases | Raw category agreement | After training-only mapping | Constant majority baseline |
| --- | ---: | ---: | ---: | ---: |
| Cecid | 10 | 100% | 100% | 100% |
| Managed Fruit Fly | 10 | 0% | 80% | 80% |
| Unmanaged Fruit Fly | 10 | 50% | 50% | 50% |

Its Fruit Fly raw scores are exactly 1.0 for all 46 months: complete infestation
in every sampled historical case. A constant raw score cannot distinguish
monthly pest activity. A mapping can assign that score a typical BPI category,
but that would measure the mapping's constant prediction rather than demonstrate
weather-sensitive forecasting. Exact Grid results and raw score ranges are
retained alongside the mapped results in the CSV/JSON artifacts.

Earlier saved reports claiming 90% overall and 100% held-out agreement used
20 filtered cases, composite weather/spatial scores, pest carryover, and fitted
class cutoffs. They remain historical artifacts. Those percentages are not
directly comparable with this full-month v16 audit and should not be carried
forward as its accuracy claim.

Across all 46 Cecid months, five observations are Medium/High under the project's
cutoffs. Both engines predict Low for every month and miss all five, yielding
89.1% agreement with no ability demonstrated to identify those larger outbreaks.
This all-period figure includes calibration observations and is descriptive,
not an independent test statistic. It shows why a high aggregate percentage
can coexist with poor outbreak detection.

## Evidence and limitations

Research supports a fruit-attacking Cecid scope and distinguishes fruit pests
from leaf midges. The UPLB record naming *P. frugivora* and the bioecology abstract
naming *P. mangivora* do not resolve the species identity of these BPI records.
The latter reports soil pupation, a 10–12-day life cycle, and adults living up
to three days. Its adult lifespan is not a measurement of this project's exact
48-hour cutoff. [Species description](https://www.ukdr.uplb.edu.ph/journal-articles/3075/),
[bioecology abstract](https://www.ukdr.uplb.edu.ph/journal-articles/4814/).

The local expert supports laying across multiple fruits/trees, a short adult
life, favorable cloudy activity, and activity during suitable rain breaks.
Those qualitative observations support the revised behavior. They do not
measure eight opportunity-hours of eggs, exact light thresholds, a 15 m hourly
cap, or a 70% protection probability. The user-mentioned cloudy-emergence study
still needs its title or source link. No inference from a leaf-midge study is
used as calibration for fruit Cecid.

The following remain assumptions needing measurements: normalized source
pressure and presence probabilities; one whole soil batch released at the first
positive score; egg depletion; survival decay; soil/rain and wind response;
cloud/radiation scales; tree/weed relay efficiency; bagging effectiveness;
external arrivals; and Fruit Fly night activity and development/source timing.
External arrivals remain a broad proxy and were excluded from this audit.
One-at-a-time tests do not identify parameter interactions or a unique set of
biologically correct coefficients.

Monthly fruit damage and adult trap catches describe different outcomes from
48-hour affected-tree predictions. Without fruit/ trap denominators and dated
host, source, treatment, and inspection records, their mismatch cannot be fixed
simply by tuning coefficients until the reported percentage increases. User
testing can establish understandable controls and useful explanations, but
cannot fill this accuracy evidence gap.

## Next work justified by these results

1. Improve the historical replay inputs: preserve a separate archive with dated
   cloud and instantaneous radiation, confirm the BPI data transcription and
   fruit-Cecid identity, and obtain measured host stages, source evidence, fruit
   samples, trap exposure, and intervention records where available.
2. Review Fruit Fly source progression and the artificial-grid saturation before
   fitting spread rates. Resolve whether newly damaged targets should become
   outgoing adult sources within the same forecast and document the output's
   relationship to trap catches.
3. Calibrate with measured inputs and historical periods reserved in advance;
   compare with simple baselines and report outbreak misses, false warnings,
   numeric error, and uncertainty rather than only overall category agreement.
4. Conduct expert/usability testing with the current explanations, then collect
   prospective dated tree/fruit observations to evaluate actual forecasts.

## Reproduction and artifacts

Verification: the full Python suite passed 768 tests. After the final historical
light-loader changes, 28 focused validation tests passed, including four new
archive-reading cases. The data files and production biological defaults were
preserved. The CSV alias selection now follows a deterministic priority rather
than set iteration, so conflicting aliases cannot vary between worker processes.

Run from the repository root:

```powershell
python -m scripts.run_revision_audit --seeds 30 --monte-carlo 10 --windows 4 --workers 4
python -m pytest tests/test_revision_audit.py -q
```

For a single part, add `--part sensitivity`, `--part bpi`,
`--part bpi_tree_graph`, or `--part light`. Use a standalone CLI process;
temporary coefficient overrides are not safe inside concurrent API requests.
The overrides restore their values even after an exception. No production
defaults are rewritten.

The tracked [sensitivity table](v16-sensitivity-summary.csv) and
[BPI results table](v16-bpi-results-summary.csv) retain compact numeric evidence.
Full reproducible artifacts live in the git-ignored
`outputs/revision-v16-audit/` directory: raw seeds, design and input hashes,
light-response probes, monthly predictions, earlier-year predictions, metrics,
and PNG charts. Regenerate them with the command above on another machine.
