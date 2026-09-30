function finiteOrNull(value) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function normalizedStage(value) {
  return value == null ? null : String(value).trim().toLowerCase()
}

export function cecidExposureRouteLabel(route) {
  if (route === 'local_and_external') return 'Local soil/habitat and outside pressure'
  if (route === 'local_soil_or_habitat') return 'Local soil source / habitat path'
  if (route === 'external_neighbor') return 'Outside-neighbor pressure only'
  return 'No adult pressure reached this tree'
}

export function interpretCecidTree(properties = {}, mode = 'likelihood') {
  const stage = normalizedStage(properties.stage ?? properties.Stage)
  const explicitEligible = typeof properties.cecid_eligible === 'boolean'
    ? properties.cecid_eligible
    : null
  const eligible = explicitEligible ?? (stage == null ? null : stage === 'fruitlet')
  const state = String(properties.state ?? properties.status ?? 'unbagged').toLowerCase()
  const representativeEstablished = state === 'infested' || state === 'infected'
  const ensembleRuns = Math.max(0, Math.trunc(finiteOrNull(properties.ensemble_runs) ?? 0))
  const ensembleCount = Math.max(
    0,
    Math.trunc(finiteOrNull(properties.ensemble_infestation_count) ?? 0),
  )
  const ensembleFrequency = finiteOrNull(properties.ensemble_infestation_frequency)
  const hasEnsemble = ensembleRuns > 1 && ensembleFrequency != null
  const cumulativeProbability = finiteOrNull(
    properties.cumulative_establishment_probability,
  )
  const peakHourlyRisk = finiteOrNull(properties.peak_hourly_risk)
  const exposureHours = Math.max(0, Math.trunc(finiteOrNull(properties.exposure_hours) ?? 0))
  const localExposureHours = Math.max(
    0,
    Math.trunc(finiteOrNull(properties.local_exposure_hours) ?? 0),
  )
  const externalExposureHours = Math.max(
    0,
    Math.trunc(finiteOrNull(properties.external_exposure_hours) ?? 0),
  )
  const representativeRisk = finiteOrNull(properties.risk)
  const displayRisk = mode === 'likelihood' && hasEnsemble
    ? ensembleFrequency
    : representativeRisk

  let outcomeLabel = representativeEstablished
    ? 'Fruit infestation established'
    : 'No fruit infestation established in this run'
  if (mode === 'likelihood' && hasEnsemble) {
    outcomeLabel = ensembleCount > 0
      ? `Established in ${ensembleCount} of ${ensembleRuns} runs`
      : `No establishment in ${ensembleRuns} runs`
  }

  let explanation
  if (eligible === false) {
    explanation = `${stage || 'Current'} stage is outside the Fruitlet hard gate.`
  } else if (representativeEstablished) {
    explanation = 'Establishment occurred in the representative stochastic draw.'
  } else if (exposureHours > 0) {
    explanation = 'Adult pressure reached this tree, but establishment did not occur in the representative draw.'
  } else {
    explanation = 'No eligible Cecid adult pressure reached this tree during the simulated windows.'
  }

  return {
    eligible,
    stage,
    representativeEstablished,
    ensembleRuns,
    ensembleCount,
    ensembleFrequency,
    hasEnsemble,
    cumulativeProbability,
    peakHourlyRisk,
    exposureHours,
    localExposureHours,
    externalExposureHours,
    exposureRoute: properties.exposure_route || 'none',
    exposureRouteLabel: cecidExposureRouteLabel(properties.exposure_route),
    displayRisk,
    outcomeLabel,
    explanation,
  }
}

