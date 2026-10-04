export const DEFAULT_IMPACT_ASSUMPTIONS = Object.freeze({
  yield_per_tree_kg: 45,
  farmgate_price_php_per_kg: 60,
  damage_low: 15,
  damage_base: 30,
  damage_high: 45,
})

export const DEFAULT_RECOMMENDATION_EFFECTIVENESS = 0.65

function parseRecord(value) {
  if (!value) return {}
  if (typeof value !== 'string') return typeof value === 'object' ? value : {}
  try {
    const parsed = JSON.parse(value)
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch (_) {
    return {}
  }
}

function finite(value, fallback) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function nonNegative(value, fallback) {
  return Math.max(0, finite(value, fallback))
}

function percentage(value, fallback) {
  return Math.min(100, nonNegative(value, fallback))
}

function effectiveness(value, fallback = DEFAULT_RECOMMENDATION_EFFECTIVENESS) {
  const parsed = finite(value, fallback)
  return Math.min(1, Math.max(0, parsed > 1 ? parsed / 100 : parsed))
}

export function normalizeImpactAssumptions(value = {}) {
  const assumptions = parseRecord(value)
  return {
    yield_per_tree_kg: nonNegative(
      assumptions.yield_per_tree_kg,
      DEFAULT_IMPACT_ASSUMPTIONS.yield_per_tree_kg,
    ),
    farmgate_price_php_per_kg: nonNegative(
      assumptions.farmgate_price_php_per_kg,
      DEFAULT_IMPACT_ASSUMPTIONS.farmgate_price_php_per_kg,
    ),
    damage_low: percentage(assumptions.damage_low, DEFAULT_IMPACT_ASSUMPTIONS.damage_low),
    damage_base: percentage(assumptions.damage_base, DEFAULT_IMPACT_ASSUMPTIONS.damage_base),
    damage_high: percentage(assumptions.damage_high, DEFAULT_IMPACT_ASSUMPTIONS.damage_high),
  }
}

export function economicInputsFromSimulation(simulation = {}) {
  const request = parseRecord(simulation.request_payload ?? simulation.input_parameters)
  const dashboard = parseRecord(request.dashboard_state)
  const assumptions = normalizeImpactAssumptions(
    simulation.impact_assumptions
      ?? request.impact_assumptions
      ?? dashboard.impact_assumptions,
  )
  const treatment = Array.isArray(request.treatment_applications)
    ? request.treatment_applications[0]
    : null
  const treatmentEffectiveness = treatment?.treatment_type === 'sanitation'
    ? treatment.source_reduction
    : (treatment?.efficacy ?? treatment?.source_reduction)

  return {
    assumptions,
    recommendationEffectiveness: effectiveness(
      treatmentEffectiveness
        ?? dashboard.treatment_efficacy
        ?? simulation.recommendation_effectiveness,
    ),
  }
}

export function calculateEconomicImpact({
  infestedCount,
  assumptions,
  recommendationEffectiveness = DEFAULT_RECOMMENDATION_EFFECTIVENESS,
} = {}) {
  if (infestedCount == null || !Number.isFinite(Number(infestedCount))) return null

  const normalized = normalizeImpactAssumptions(assumptions)
  const affected = nonNegative(infestedCount, 0)
  const effectivenessRate = effectiveness(recommendationEffectiveness)
  const cropValueAtRisk = affected
    * normalized.yield_per_tree_kg
    * normalized.farmgate_price_php_per_kg
  const projectedLoss = cropValueAtRisk * (normalized.damage_base / 100)
  const estimatedSavings = projectedLoss * effectivenessRate

  return {
    infested_count: affected,
    yield_per_tree_kg: normalized.yield_per_tree_kg,
    farmgate_price_php_per_kg: normalized.farmgate_price_php_per_kg,
    damage_rate: normalized.damage_base / 100,
    recommendation_effectiveness: effectivenessRate,
    projected_loss: projectedLoss,
    estimated_savings: estimatedSavings,
    remaining_loss: Math.max(0, projectedLoss - estimatedSavings),
  }
}

export function calculateSimulationEconomicImpact(simulation = {}, { infestedCount } = {}) {
  const inputs = economicInputsFromSimulation(simulation)
  return calculateEconomicImpact({
    infestedCount: infestedCount ?? simulation.n_infested_final,
    assumptions: inputs.assumptions,
    recommendationEffectiveness: inputs.recommendationEffectiveness,
  })
}

export function formatPhp(value) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return '—'
  return `PHP ${Math.round(parsed).toLocaleString('en-PH')}`
}
