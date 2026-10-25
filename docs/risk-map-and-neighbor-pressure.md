# Geographic risk heatmap and multiple neighbors

The surrounding satellite background uses Esri World Imagery, underneath each
orchard's separate orthophoto. Live checks on 25 October 2026 found available
zoom-18 tiles at BPI and Guimaras Wonders Farm, but missing zoom-19 and zoom-20
tiles. The detail source therefore stops requesting new tiles at zoom 18 and
enlarges those images as the camera zooms closer. A separate zoom-15 satellite
underlayer supplies coarser context if a detail tile is missing; OpenStreetMap
remains underneath both. All background layers remain enabled at close zooms.
Esri requests use [`blankTile=false`](https://developers.arcgis.com/rest/services-reference/enterprise/map-tile/)
so missing tiles return 404 instead of covering the fallback with an opaque
"Map data not yet available" picture. Background coverage still depends on the
providers and network availability.

At these latitudes the fallback tiles have a ground sampling of approximately
4.7 m per tile pixel; that is not a claim of measured image resolution or
positional accuracy. The live map's metric scale bar shows actual distances
(including a 5 m bar at suitable close zooms). Enlarging a satellite tile adds
no new photographic detail. The existing orchard orthophotos, tree locations
and report-only orthophoto map are unchanged.

Collapsing the workspace keeps the existing map instance and imagery mounted.
MapLibre's own container resize observer resizes and redraws the canvas together;
there is no second observer clearing the canvas between animation frames. The
controls slide and fade at a fixed content width to avoid reflow while collapsing.
The transitions are disabled when the user requests reduced motion.

The heatmap is a geographic canvas raster anchored to fixed Mercator coordinates.
It uses the existing green/yellow/orange/red/dark-red risk palette. Tree centers
anchor the surface to the same normalized risk and eligibility as their markers;
soft shading interpolates between them. Gaussian falloff uses ground distances
(8–16 m bandwidth based on tree spacing, with a three-bandwidth cutoff), never
screen pixels or map zoom. This display smoothing is not a modeled flight range
or a measurement of infestation between trees.

Zero-risk, dead, missing-risk, and Cecid-ineligible trees constrain interpolation
instead of contributing heat. Point anchors also protect all four raster texels
used by bilinear resampling. At extremely close spacing or coarse resolution,
lower-risk anchors take priority where texels overlap. Grid-cell interiors and
polygon holes retain their supplied values; smoothing fills the surrounding gaps.
Normalized interpolation prevents dense clusters from artificially increasing
the simulation's risk. Zooming changes screen size, not geographic coverage or
the risk surface. Playback and the selected Cecid view update the same canvas
with the current frame's values, without removing the visible layer or fetching
a replacement PNG. The camera fits when orchard geometry changes, rather than
on every risk update. Export waits for the current canvas to render. Hour zero
clears heat when its supplied risks are zero, and playback stops at the final
hour without wrapping during slow rendering.

Per-tree **History Infected** identifies a possible residual soil/adult reservoir.
It remains initially uninfested and normally susceptible; an activated reservoir
can contribute local adult pressure without declaring current fruit infestation.
For Cecid it supplies a soil anchor governed by the existing emergence/cohort
model. For Fruit Fly it supplies a separate local reservoir pressure, rather
than a forced infected-tree state. **Suspect** identifies a possible current
infestation: when its source-presence draw succeeds it starts infested, otherwise
it remains susceptible. Both are labeled assumed rather than observed sources.
**Infected** remains a fixed current source for the selected scenario.

`history_source_probability` and `suspect_source_probability` set each candidate's
per-realization presence chance from 0 to 1. Both default to 0.5 as uncalibrated
scenario assumptions, not measured BPI probabilities. Presence draws use a
replay-stable RNG independent of infestation-establishment draws. Historical or
suspected evidence suppresses arbitrary healthy-tree fallback even if all such
draws are absent. Possible sources can be sampled alongside known infections.
Bagging reduces each incoming contribution by 70%, leaving 30%; it does not
remove an existing infestation or a historical reservoir at that location.
Changes to tree status apply to a new run; saved simulation frames retain their
recorded values.

Both API modes honor imported `status`/`Status` values as well as manual
overrides, including `unbagged`/`infested` aliases. Existing infected trees
suppress automatic healthy-tree source selection for either pest. Unknown-source
fallback selects ordinary unbagged trees only when no source evidence is supplied;
it never seeds a bagged or dead tree automatically. Dead trees are also excluded from ordinary
Cecid resting nodes. A separately supplied soil-habitat source can still exist
at that ground location, independently of whether the tree is alive. The status
selector maps simulation aliases back to Healthy/Infected correctly.

For either pest, **Across runs** colors infestation frequency (established outcomes
divided by ensemble runs). **One run** colors the representative run's risk
score, which becomes 100% after an infestation establishes. A representative
100% score therefore does not imply 100% ensemble frequency. Tree details,
popups, and field-verification prefills use the active map's value; the legend
labels the selected metric. The color cutoffs remain 10%, 25%, 50%, and 75%.

Hovering over a tree, or focusing its marker with the keyboard, opens a read-only
details card. It shows the tree number, current status before a forecast, or the
one-run status and active map metric when displaying a saved result. Available
stage, source and Cecid exposure details retain their scenario/model labels;
hovering does not turn a prediction into a field observation. The card remains
open while the pointer is over it, and closes on Escape, leaving the tree/card,
or moving the map. Click the tree or press Enter to open the existing Tree
Management controls. Touch users still tap a tree to manage it. Hover/focus
alone changes no tree inputs and sends no application writes.

Repeated-run maps are implemented for Cecid and Fruit Fly. The UI offers 1,
5, or 9 realizations (default 5), and restores saved choices. API callers default
to 1. `uncertainty_runs` applies to either pest; when supplied it takes precedence
over legacy `cecid_uncertainty_runs`. `metadata.uncertainty_summary` is generic;
Cecid retains its legacy summary alias for compatibility.

Additional realizations keep weather, neighbor settings, treatments, geometry,
model coefficients, known sources, and representative per-tree stages fixed.
They vary infestation-establishment draws, historical/suspected source presence,
and random fallback source counts/placement when no source evidence is supplied.
Fruit Fly's directed-neighbor edge selection remains a fixed assumed placement;
it is not silently described as resampled source-location uncertainty. Summary
metadata records placement modes and whether sampled source-location sets differ.
Across-runs frequencies describe the final result; One run and playback show the
first, reproducible realization. Reports and spreadsheets keep frequency separate
from that realization's scores, and include source-presence settings/provenance.
Known source locations reduce starting-location uncertainty but do not remove
stochastic establishment or establish field accuracy. Frequencies are conditional
model outcomes; tree-level forecasting accuracy requires observed field outcomes.

Isolated Cecid outcomes do not imply a direct flight from the nearest S marker.
S markers identify local soil-source anchors. Existing adult cohorts can move
through uninfested fruitlet trees and weed relay nodes, with local hops capped at
15 m per eligible hour; infestation at every intermediate tree is not required.
Neighbor pressure is a separate external-arrival proxy, applied directly to
eligible trees with positive directional pressure, without a connection to S.
Directional pressure covers the facing half of the orchard projection; All sides
is uniform. Outside orchard coordinates, distances, and flight paths are not
represented, so the local 15 m movement cap does not constrain external arrivals.
Individual establishment draws can yield isolated outcomes. Tree details report
local/outside exposure hours for the representative run, not proof of the exact
source that caused infestation. These are model assumptions to explain and
validate, rather than evidence of observed insect travel.

Simulation > Model & Neighbor Pressure > Add neighbor accepts up to 16 orchards.
Each has a name, its own threat from 0 to 1, and a compass direction describing
where the outside orchard lies. All sides preserves uniform pressure when a
source's direction is unknown. Multiple orchards may share a direction.

The API accepts `neighbor_sources`, for example:

```json
{
  "neighbor_sources": [
    {"label": "North orchard", "direction": "N", "threat": 0.4},
    {"label": "East orchard", "direction": "E", "threat": 0.6}
  ]
}
```

An explicit list replaces the legacy `neighbor_threat` and `neighbor_direction`.
An empty list disables external pressure. Omitting the list keeps the legacy
single-source inputs supported. Saved requests, result metadata, reports, and
Excel history exports retain all sources.

For each target, source i contributes spatial pressure `t_i` using the existing
directional edge gradient (or uniform pressure for All sides). Its wind factor is
`f_i = clip(1 + WIND_NEIGHBOR_BOOST * cos(wind_from - source_bearing), 0, 2)`.
The effective pressure is:

```
T = sum(t_i)
effective_pressure = min(1, T) * sum(t_i * f_i) / T   when T > 0
effective_pressure = 0                              otherwise
```

Thus local pressure is capped before wind, every source keeps its bearing, and
one source preserves the single-source equation. Final infestation probabilities
remain bounded by the simulation's existing probability update. This is a
scenario proxy, not a newly calibrated estimate of infestation or distance.
Fruit Fly automatic seeding includes each supplied directional edge and removes
duplicate seeds. Cecid outside arrivals remain separate from local soil sources
and still obey phenology, twilight/cloudy daylight, weather, bagging, and treatment conditions.

Grid rows increase latitude in the API's geographic output. Directional neighbor
pressure and automatic source ranking now use increasing rows for north. Fruit
Fly grid dispersal uses `atan2(column_delta, row_delta)` for its compass bearing;
its previous negative row delta reversed north/south and the four diagonal
bearings. East/west bearings were correct. Tests cover all eight compass bearings,
both Fruit Fly calculation paths, Cecid local dispersal, wind-from versus travel
direction, and both grid and tree-graph neighbor pressure and source selection.
Legacy and multiple-source directions accept the same validated compass values.
New runs record model version `2026.10-source-scope-v13`; older stored snapshots
stay readable, but re-running a scenario uses the corrected direction and status
behavior.

See [Cecid reliability plan](cecid-reliability-plan.md) for the proposed boundary
arrival model, the source/timing evidence to collect, and a field-testing plan.
