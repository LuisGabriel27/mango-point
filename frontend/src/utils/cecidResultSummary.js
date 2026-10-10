import { simulationUncertaintySummary } from './simulationMapInterpretation.js'

function finiteNumber(value, fallback = 0) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

export function summarizeCecidResult(simulation) {
  const metadata = simulation?.metadata ?? {}
  const stageBreakdown = metadata.stage_breakdown ?? {}
  const eligibleTreeCount = Math.max(0, finiteNumber(stageBreakdown.fruitlet))
  const establishedTreeCount = Math.max(0, finiteNumber(simulation?.n_infested_final))
  const orchardTreeCount = Array.isArray(simulation?.risk_geojson?.features)
    ? simulation.risk_geojson.features.length
    : Object.values(stageBreakdown).reduce((total, value) => total + finiteNumber(value), 0)
  const diagnostics = Array.isArray(simulation?.gate_diagnostics)
    ? simulation.gate_diagnostics
    : (Array.isArray(metadata.cecid_habitat_diagnostics)
        ? metadata.cecid_habitat_diagnostics
        : [])
  const reachableTreeCount = diagnostics.reduce(
    (maximum, entry) => Math.max(maximum, finiteNumber(entry?.reachable_tree_count)),
    0,
  )
  const externalNeighborTreeCount = diagnostics.reduce(
    (maximum, entry) => Math.max(
      maximum,
      finiteNumber(entry?.external_neighbor_exposed_tree_count),
    ),
    0,
  )
  const uncertainty = simulationUncertaintySummary(simulation)

  return {
    establishedTreeCount,
    eligibleTreeCount,
    orchardTreeCount,
    establishedEligibleRate: eligibleTreeCount > 0
      ? establishedTreeCount / eligibleTreeCount
      : null,
    establishedOrchardRate: orchardTreeCount > 0
      ? establishedTreeCount / orchardTreeCount
      : null,
    reachableTreeCount,
    externalNeighborTreeCount,
    sourceCount: Math.max(0, finiteNumber(metadata.cecid_source_count)),
    assumedSourceCount: Math.max(0, finiteNumber(metadata.cecid_assumed_source_count)),
    cohortEventCount: Array.isArray(metadata.cecid_cohort_events)
      ? metadata.cecid_cohort_events.length
      : 0,
    uncertainty,
  }
}
