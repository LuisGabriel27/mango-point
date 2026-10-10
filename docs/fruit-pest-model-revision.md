# Fruit pest model revision — October 2026

Model version: `2026.10-daylight-light-v16` (extends the v15 moisture revision).

## Scope and evidence

Cecid refers to the Philippine fruit-attacking mango midge, provisionally
identified as *Procontarinia frugivora*. Leaf and blossom midges are excluded.
The [Gagné and Medina species description](https://www.ukdr.uplb.edu.ph/journal-articles/3075/)
identifies *P. frugivora* as a Philippine mango pest. The local species should
still be confirmed by BPI identification.

The [2013 Medina, Pamiloza and Velasco abstract](https://www.ukdr.uplb.edu.ph/journal-articles/4814/)
uses the name *P. mangivora*. It reports fruit attack, soil pupation, a 10–12
day life cycle, adult life up to three days, and evidence against exclusive
nocturnal activity. It distinguishes fruit-attacking from leaf-attacking
midges. The naming relationship with *P. frugivora* has not been independently
resolved here; the abstract does not prove the model's hourly coefficients.

The project's expert observations support a 1–2 day adult scenario, laying
across several fruits/trees before egg exhaustion, wind-assisted movement,
and cloudy-day movement. These are recorded as expert evidence. The study
the user mentioned for cloudy-day soil emergence is still awaiting its title
or link. The daylight exception now requires radiation evidence alongside cloud
cover, or an explicit observed/assumed daylight condition. Its response scales
remain provisional, with separate scores for emergence and movement.

Fruit Fly refers to *Bactrocera dorsalis*. [Choi et al. (2020)](https://pmc.ncbi.nlm.nih.gov/articles/PMC7363081/)
observed laboratory oviposition at 23.5 °C, supporting removal of a universal
25 °C cutoff. [Hidaka et al. (2026)](https://pmc.ncbi.nlm.nih.gov/articles/PMC12940858/)
found outdoor flight initiation peaks around 10:00 and sunset and intermittent
flight in darkness on flight mills. Peak hours are not exclusive activity
hours. Flight-mill evidence does not establish ordinary orchard oviposition
at night, and neither paper measures this model's per-tree spread probability.
The expert's susceptible stage is represented as green mature through ripening.

## Cecid lifecycle

Each configured local soil source has one normalized emergence batch shared
across the 72-hour antecedent replay and the forecast. The emergence score
evaluates current soil moisture and activity without a separate rain-arming
requirement. Rain adds to a moisture proxy but never adds insects to the reservoir.
This is a conservative finite
supply assumption, not a finding that real soil populations emerge all at once.
Any positive emergence score can open that batch; the score is not a fitted
fraction emerging per hour. A continuous soil-population release model needs data.
No immature population counts or replenishment observations are available.

An emerged cohort starts with egg capacity 1. Its pressure is:

`base source pressure × 2^(-age / 24 hours) × remaining egg capacity`.

Laying opportunity weights are pooled across reachable fruitlet targets,
capped at one per cohort per hour, and divided by the configurable
`CECID_EGG_CAPACITY_HOURS` value (default 8). Eight full opportunity hours
exhaust the initial capacity; weaker opportunities use smaller fractions.
These are relative units, not an insect count, eggs per fruit, or an observed
eight-hour oviposition period. Tests compare 4, 8, and 16 opportunity-hour settings.

Egg capacity is spent before the establishment draw and target protection
modifiers. This deliberately separates attempted laying exposure from
successful infestation, including already affected fruit. It approximates
possible wasted eggs; it does not measure egg deposition on bagged fruit.
Dead trees and non-fruitlet hosts do not consume eggs.

A cohort continues movement/resting across trees while it retains capacity.
It stops contributing after exhaustion or at age 48 hours. Partial laying
does not remove the whole cohort after its first affected tree. Infested fruit
stays infested when the adult cohort ends; it does not generate an immediate
replacement adult cohort. The 24-hour pressure half-life and strict 48-hour
maximum are scenario settings requiring survival data.

## Weather and host rules

| Rule | Implemented behavior | Evidence status |
| --- | --- | --- |
| Cecid twilight | Solar dawn/dusk activity weight 1 | Expert-informed window; hourly width remains assumed |
| Cecid cloudy daylight | Weight `0.6 × daylight light score`; cloud percentage alone cannot open it | Qualitative expert support; light response and maximum uncalibrated |
| Cecid darkness | No cloudy-day exception outside daylight/twilight | Model assumption |
| Soil emergence | Soil wetness × current drying × activity | Rain is a soil-moisture proxy; no humidity cutoff invented |
| Existing adult movement | Current drying × wind activity × activity | Independent of local soil wetness |
| Fruit Fly host | `mature` includes green mature through ripening | Expert stage clarification |
| Fruit Fly activity | Daylight 1, outside-daylight twilight 0.5, darkness 0.02 | Reduced night allowance is assumed, not measured oviposition |
| Fruit Fly temperature | `clamp((T − 25) / 10 + 1, 0, 1.5)` | Continuous response is provisional; exact curve not fitted to the paper |

The Q3 change adds **Moist now** to custom soil controls. It initializes a
relative moisture score at forecast Hour 0 without inventing rain in the
preceding 72 hours. A score of 1 maps to the selected moisture sensitivity
scale; it is not volumetric soil-water content, saturation, or air humidity.
The UI expresses this relative score as 0–100% of the model scale.

API clients can also supply `cecid_initial_soil_moisture_score` (0–1) for live
or custom simulation weather. This explicit value takes precedence over the
moist preset. Without either input, the existing decayed rainfall estimate is
used. An explicit Hour 0 state replaces that antecedent moisture estimate,
decreases with the provisional 48-hour moisture half-life, and receives rain
from the forecast hours only. It does not rewrite or replenish adult cohorts
that already emerged during antecedent replay.

No fresh wetting event or completely dry hour is required to release a soil
batch. For example, an existing soil population under assumed moist conditions
can emerge at a supported dim-overcast noon with zero recorded rain. A 0.5 mm/h drizzle reduces
the emergence and movement scores rather than acting as a second source
closure. The retained current-rain curve reaches zero at 1 mm/h; that scale
is provisional. Dry soil, absent immature populations, incompatible host stage,
and closed activity windows still prevent local emergence. No hard humidity
cutoff has been introduced.

The optional `fruit_fly_temp_threshold_c` request field still provides a hard
experimental cutoff when explicitly supplied. Without it, 25 °C is a reference
point in the continuous curve. This inherited simple curve does not model
heat stress or a fitted high-temperature optimum.

Both engines use these activity rules. Open-Meteo requests include `cloud_cover`,
`shortwave_radiation_instant` and `direct_normal_irradiance_instant`. They map to
`cloud_cover_pct`, `shortwave_radiation_wm2` and `direct_normal_irradiance_wm2`.
The instant variables are estimates at the indicated time; the ordinary radiation
variables average the preceding hour and are deliberately not substituted.
Missing or invalid radiation stays unknown, including when cloud cover is high.
Synthetic weather generates separately labeled light estimates without changing
the existing temperature/wind/rain random sequence.

## Cloud cover and daylight light evidence

Open-Meteo defines total cloud cover as an area fraction, not a reduction in
sunlight or a measurement beneath each tree. Thin clouds can transmit sunlight.
[Open-Meteo definitions](https://open-meteo.com/en/docs),
[Met Office cloud explanation](https://weather.metoffice.gov.uk/learn-about/weather/types-of-weather/clouds/high-clouds).

For live daylight, both total horizontal shortwave radiation (GHI) and direct
normal irradiance (DNI), plus cloud cover and a dated orchard position, are
required. An approximate clear-sky GHI reference uses
[NOAA solar position](https://gml.noaa.gov/grad/solcalc/solareqns.PDF) and the
[Haurwitz clear-sky model](https://pvlib-python.readthedocs.io/en/stable/reference/generated/pvlib.clearsky.haurwitz.html).
This normalizes for sun elevation/date/time; it is not measured orchard light
and does not account for canopy, aerosols or local atmospheric observations.

The provisional brightness ratio is the larger of `GHI / clear-sky GHI` and
`DNI / 800 W/m²`. A ratio of at least 0.8 closes the daytime exception even
under high cloud cover; at most 0.25 gives full dimness. Intermediate ratios
interpolate linearly. Cloud strength is zero up to 50% cover, interpolates
between 50% and 80%, and is one from 80%. The daylight light score is dimness
times cloud strength. These scales are explicit project assumptions, not
research-confirmed insect thresholds; they require sensitivity tests and local
light/activity observations. They prevent a tiny cloud reading from releasing
the source's entire modeled batch. Strong diffuse daylight can also close the
exception, even when DNI is zero.

Custom periods offer **Bright sunshine**, **Intermittent sunshine**, and
**Dim overcast**, independently of cloud percentage. Their relative light
scores are 0, 0.5 and 1; the activity maximum remains 0.6. API clients use
`daylight_condition` values `bright_sunshine`, `intermittent_sunshine`, or
`dim_overcast`, with `daylight_condition_basis` set to `assumed` or `observed`.
Omitted basis defaults to assumed. Observed means a user's reported local
daylight condition, not sensor verification. The explicit condition takes
precedence over radiation/cloud inference; a dim-overcast scenario can therefore
represent a local condition that a regional cloud estimate missed. No condition
opens the cloudy-day exception in darkness, and existing host/rain/soil/wind
rules still apply. A weather pause does not reset adult age or egg capacity.

**Tree-canopy shade alone never enables emergence or movement.** It is not an
accepted daylight condition. Tree/weed resting locations retain their habitat
role, without opening weather activity or supplying another generation.

Older saved cloud-only schedules remain readable, but rerunning them under
v16 does not infer daytime light from cloud percentage alone. Select an
explicit daylight condition for a controlled scenario. Dawn/dusk rules retain
their existing behavior even when radiation is unavailable. Playback weather,
gate/habitat diagnostics and alert context record the light evidence and basis.

`suitability_score` and favorable Cecid alerts describe **emergence weather**.
They do not confirm insects are present. Diagnostics additionally expose
`movement_score`, `emergence_score`, `movement_available`, and
`emergence_available`; adults arriving from outside can move even with dry
local soil. Cloudy-day alerts identify their activity window explicitly.

## Interpretation and remaining limits

Run metadata records the Cecid species, scope, capacity rate, finite reservoir,
lifespan, and cloud assumptions. Hourly habitat diagnostics report remaining
egg capacity and spent/expired cohorts. Saved results remain readable; rerunning
an old request uses the current version and may produce different outcomes.

The external-neighbor pressure remains a broad hourly arrival proxy. It is not
a tracked finite local cohort, a boundary-crossing simulation, or proof of
individual orchard-wide travel. The 15 m movement limit, wind coefficients,
source-presence probabilities, bagging protection, and weed relay strengths
remain provisional. Fruit Fly generation timing also needs separate validation.

Regression checks cover partial depletion, exhaustion, expiry, multiple-tree
movement, no instant second Cecid generation, failed establishment, antecedent
replay, cloudy/clear/dark activity, missing clouds, temperature behavior, and
saved weather schedules, bright cloudy skies versus dim overcast, missing
radiation, low sun elevation, canopy-shade exclusion, and the four-hour rain /
one-hour dim break / renewed-rain scenario in both engines. Passing these verifies implementation consistency;
it does not establish predictive biological accuracy. Next field work should
measure survival, laying/establishment separately, soil emergence supply, and
cloud/light response for the identified fruit-attacking species.
