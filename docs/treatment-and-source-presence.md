# Treatment and source-presence scenarios

The dashboard sends one treatment application when enabled. At effectiveness
`e`, the affected factor becomes `1 - e`; 65% leaves 35% of that contribution.
These are scenario assumptions, not pesticide-specific efficacy measurements.

| Scenario | Default coverage | Incoming susceptibility | Outgoing local source pressure |
| --- | --- | --- | --- |
| Protective | All living orchard trees/cells | Reduced by e | Unchanged |
| Targeted | Initial active source locations | Reduced by e | Reduced by e |
| Sanitation | Initial active source locations | Unchanged | Reduced by e |
| Combined | All living orchard trees/cells | Reduced by e | Reduced by e |

Treatments apply once before the first simulated hour. Factors stay constant
through the forecast; there is no decay, reapplication, or cure of existing
infestation. Default targeted coverage includes observed infections, active
Suspect hypotheses, active History reservoirs, and selected initial source
anchors. Absent hypotheses are excluded. The selection does not expand when
another tree becomes infested. The API also supports explicit target lists.
Dead trees and empty cells are excluded, including from explicit targets.
Sanitation reduces local sources; it does not remove outside neighbor pressure.
Grid coverage counts occupied cells, while tree-graph coverage counts trees.

## Source presence at a zone or tree

Status zones support an optional `source_probability` between 0 and 1 for
History Infected and Suspect. The editor offers **Use scenario default** or
**Set a percentage**. Infected displays **100% (confirmed)** and stays fixed.
Healthy, Bagged, and Dead do not offer uncertain-source settings.

- History Infected may retain a soil anchor (Cecid) or an adult reservoir
  (Fruit Fly). Source presence does not start its fruit as infested.
- Suspect may contain a current infestation. An active realization starts
  that tree as infested; an inactive one leaves it susceptible.
- Each candidate is sampled independently per realization. A 70% zone value
  means a 70% presence assumption for each candidate, not a 70% infection-risk
  prediction or one shared activation event for the entire zone.

Later overlapping status zones take precedence. An individual tree percentage
overrides its zone; explicitly choosing the scenario default also overrides
the zone percentage. Applying a new zone clears earlier individual source
settings for its covered trees. Orchard refresh preserves the zone order.

The dashboard resolves the percentages into
`tree_source_probability_overrides` on SimulationRequest. Missing entries use
the History/Suspect defaults under Model. Confirmed infections and dead trees
cannot be disabled/revived by this dictionary. Presence draws stay separate
from establishment draws and reproduce with the same seed.

**Apply to orchard** stores the zone percentage in the existing status-zone
JSON. **Scenario only** and individual tree overrides stay with the current
scenario and its saved simulation inputs. Saved templates restore both the
zone values and individual choices, including an explicit default choice.
Zone records and the report display custom percentages; each realized source
record retains its actual probability and presence result.

Model version `2026.10-source-scope-v13` distinguishes the corrected historical
reservoir treatment coverage from earlier saved results.
