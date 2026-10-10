# Cecid model reliability: evidence and next changes

The [October fruit pest revision](fruit-pest-model-revision.md) now includes
finite local egg capacity, a 48-hour adult scenario, and cloudy daylight
activity. The 1–2 day lifespan and cloud response are expert-informed settings;
their quantitative coefficients still need species-specific field calibration.
The Q3 follow-up removes independent rain arming: an explicit Hour 0 moisture
scenario can support existing soil populations without fabricated antecedent rain.
Its moisture scale and decay remain assumptions, not measured soil-water content.
The v16 daylight revision requires cloud plus solar-radiation evidence, or an
explicit observed/assumed daylight condition. Cloud fraction or tree-canopy
shade alone cannot open daytime emergence/movement. Bright-cloudy/dim-overcast
and rain-break checks establish implementation consistency; the light-response
scales remain uncalibrated assumptions requiring sensitivity and field tests.

The [v16 sensitivity and BPI audit](v16-sensitivity-and-bpi-validation.md)
now records the controlled experiments and historical comparison. Egg capacity
materially affects results; perfect category agreement in the all-Low 2025
Cecid period does not demonstrate outbreak detection. Quantitative field
calibration and stronger historical inputs remain necessary.

The [updated original validation defense](v16-validation-defense.md) separately
retains the legacy 20-case calendar, composite score, and observed BPI carryover
for both current engines. Its five 2025 test classes are also perfectly matched
by the training-majority baseline; present this historical comparison alongside
the broader audit rather than treating it as independent forecast accuracy.

The current neighbor-pressure calculation contributes outside-adult exposure
directly to eligible trees with positive directional pressure. Its footprint is
the facing half of the orchard projection (or all trees for an unknown
direction). It does not place an outside orchard on the map, reconstruct a
boundary crossing, or constrain that crossing by the local adult movement
network. This is the main reason an isolated outcome can occur far from a
marked local soil-source hotspot. A scattered map alone neither verifies nor
disproves the model.

## Changes included in the source/ensemble release

- Bagging leaves 30% of an incoming contribution. The chosen 70% reduction is
  a project scenario setting, not a measured universal bagging effectiveness.
- History Infected can identify a possible residual reservoir while the tree
  remains initially uninfested. Suspect can identify a possible current
  infestation. Presence is sampled independently per realization using
  adjustable scenario probabilities; the initial 50% defaults express an
  uncalibrated assumption, not a BPI estimate.
- Known infections stay fixed. Historical/suspected evidence suppresses
  arbitrary healthy-tree fallback even if no candidate is activated in a run.
- Both pests can report repeated-run infestation frequency. Tree stages from
  the representative realization are pinned for additional runs, so changing
  the random seed does not silently change the orchard's phenology.

## First priority: explicit outside entry

Replace direct orchard-wide outside contributions with boundary arrival nodes:

1. Use the orchard boundary and each neighbor's direction to identify entry
   segments. Add actual neighbor location/distance when those are available;
   direction alone does not determine an outside flight distance.
2. Create an external adult cohort at those entry segments during eligible
   conditions. Keep its provenance distinct from local soil emergence.
3. Move that cohort through the same adult habitat network used by local
   sources. Apply the same time step, distance cap, weather activity, age decay,
   bagging, and treatment effects. Never infect a remote tree merely because
   its directional pressure is positive.
4. Record first reachable time and local/external exposure separately. A
   reachable tree need not have infected intermediate trees: movement and
   successful establishment remain different events.
5. Keep the existing broad arrival proxy as an explicitly labeled legacy mode
   for old run replay. Report the chosen arrival model in new-run metadata.

This would make movement assumptions traceable; it would not by itself prove
that the movement rates match Guimaras field conditions. Do not force a smooth
cluster merely to make the map easier to defend.

## Second priority: source and timing evidence

Ask BPI to confirm the target Cecid species, when historical damage indicates
remaining soil populations, time since infestation, sanitation effects, and
how source confidence should change with those observations. Obtain observed
adult activity windows, emergence timing after rainfall, and movement distances.
The current 15 m per eligible hour, twilight/cloud activity, resting efficiencies, and
source strengths require local evidence rather than visual tuning.

Medina, Pamiloza, and Velasco's 2013 field/laboratory abstract for
*Procontarinia mangivora* reports soil pupation, a 10–12 day life cycle, and adult
life up to three days. It also cautions against treating this fruit-attacking
species like the leaf-attacking Cecid species. These findings support examining
soil sources, but do not establish a 50% historical-source probability, a 15 m
hourly movement cap, or an exclusive twilight activity window.
[UPLB research record](https://www.ukdr.uplb.edu.ph/journal-articles/4814/).

DA-BAFS's 2025 mango GAP manual discusses bagging timing and fruit protection
materials. It does not establish the system's chosen 70% reduction. Record
bagging date, coverage, damage, and material when calibrating protection.
[DA-BAFS mango GAP manual](https://bafs.da.gov.ph/wp-content/uploads/2025/05/2025_EM-GAP-Mango_compressed.pdf).

## Third priority: test predictions against future observations

Record per-tree pest identification, stage, observed status, dated damage,
source evidence, bagging, sanitation/treatment, and actual neighbor positions.
Use observations before the forecast to set inputs; retain later observations
for testing. Inspect high, medium, and low predicted-frequency trees, including
controls. Measure missed infestations, false alarms, frequency calibration, and
time/location of first observations across multiple orchard/weather episodes.

Run controlled comparisons before and after a boundary-entry change:

- A single known local source with outside pressure disabled.
- A single northern outside source with all local sources disabled.
- Two opposing outside sources with a fixed fruitlet stage map.
- Historical/suspected source presence set to 0 and 1, then uncertain values.
- The same cases with bagging, treatment, dead trees, and disconnected habitat.

For each case, assert that heatmap anchors match the supplied metric, known
sources stay fixed, absent sources remain absent, and remote first-hour outcomes
require a valid arrival route. Compare multiple realizations rather than one
favorable screenshot. Existing monthly BPI monitoring aggregates support
historical plausibility checks; they cannot validate tree-level flight paths.

The acceptance goal is explanatory consistency and measured forecasting skill,
not a visually continuous heatmap.
