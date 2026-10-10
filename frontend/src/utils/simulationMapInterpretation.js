function finiteOrNull(value) {
  if (value == null || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

export function simulationUncertaintySummary(simulation) {
  return simulation?.metadata?.uncertainty_summary
    ?? simulation?.metadata?.cecid_uncertainty_summary
    ?? null
}

export function simulationEnsembleRuns(simulation) {
  const summaryRuns = Number(simulationUncertaintySummary(simulation)?.runs ?? 0)
  const featureRuns = Math.max(0, ...(simulation?.risk_geojson?.features || []).map(
    (feature) => Number(feature.properties?.ensemble_runs) || 0,
  ))
  return Math.max(summaryRuns, featureRuns)
}

export function interpretSimulationTree(properties = {}, mode = 'likelihood') {
  const state = String(properties.state ?? properties.status ?? 'unbagged').toLowerCase()
  const representativeEstablished = state === 'infested' || state === 'infected'
  const ensembleRuns = Math.max(0, Math.trunc(finiteOrNull(properties.ensemble_runs) ?? 0))
  const ensembleCount = Math.min(ensembleRuns, Math.max(
    0, Math.trunc(finiteOrNull(properties.ensemble_infestation_count) ?? 0),
  ))
  const rawFrequency = finiteOrNull(properties.ensemble_infestation_frequency)
  const ensembleFrequency = rawFrequency == null ? null : Math.max(0, Math.min(1, rawFrequency))
  const hasEnsemble = ensembleRuns > 1 && ensembleFrequency != null
  const representativeRisk = finiteOrNull(properties.risk)
  const displayMode = mode === 'likelihood' && hasEnsemble ? 'likelihood' : 'representative'
  return {
    representativeEstablished, ensembleRuns, ensembleCount, ensembleFrequency, hasEnsemble,
    displayMode,
    displayRisk: displayMode === 'likelihood' ? ensembleFrequency : representativeRisk,
    displayRiskLabel: displayMode === 'likelihood'
      ? 'Infestation frequency across runs' : 'One-run risk score',
    displayExplanation: displayMode === 'likelihood'
      ? 'Map colors show the share of repeated runs in which infestation was present. Weather and known stages stay fixed; uncertain sources and establishment draws can vary.'
      : 'This score belongs to one simulated run. Infestation is shown as 100%; it does not mean 100% likelihood across repeated runs.',
    outcomeLabel: displayMode === 'likelihood'
      ? (ensembleCount > 0 ? `Infested in ${ensembleCount} of ${ensembleRuns} runs` : `No infestation in ${ensembleRuns} runs`)
      : (representativeEstablished ? 'Infestation present in this run' : 'No infestation in this run'),
  }
}

export function initialSourceDetails(properties = {}, pestType = 'fruitfly') {
  if (!properties.initial_source) return null
  const assumed = Boolean(properties.initial_source_assumed)
  const origin = String(properties.initial_source_origin ?? '')
  const reservoir = /history|reservoir/.test(origin)
  return {
    assumed, origin,
    badge: reservoir && pestType === 'fruitfly' ? 'R' : 'S',
    label: properties.initial_source_label
      || (reservoir ? 'Possible pest reservoir' : assumed ? 'Possible current source' : 'Known current source'),
    explanation: assumed
      ? 'Source presence was assumed in this run. This is a scenario assumption, not a confirmed field observation.'
      : 'Recorded current source for this simulation.',
  }
}

export function selectableTreeStatus(value) {
  const status = String(value ?? 'healthy').trim().toLowerCase().replace(/\s+/g, '_')
  return status === 'unbagged' ? 'healthy' : status === 'infested' ? 'infected' : status
}

export function resolveTreeStatuses(properties = {}, overrideStatus) {
  const normalize = (value) => String(value ?? 'healthy').trim().toLowerCase().replace(/\s+/g, '_')
  const inputStatus = normalize(overrideStatus ?? properties.status ?? properties.Status ?? properties.state)
  return { inputStatus, status: normalize(properties.state ?? inputStatus) }
}
