import test from 'node:test'
import assert from 'node:assert/strict'
import {
  calculateEconomicImpact,
  calculateSimulationEconomicImpact,
  economicInputsFromSimulation,
  formatPhp,
} from './economicImpact.js'

test('calculates projected loss, potential savings and remaining loss from saved assumptions', () => {
  const result = calculateEconomicImpact({
    infestedCount: 10,
    assumptions: {
      yield_per_tree_kg: 50,
      farmgate_price_php_per_kg: 70,
      damage_base: 40,
    },
    recommendationEffectiveness: 0.6,
  })

  assert.equal(result.projected_loss, 14_000)
  assert.equal(result.estimated_savings, 8_400)
  assert.equal(result.remaining_loss, 5_600)
  assert.equal(result.recommendation_effectiveness, 0.6)
})

test('restores assumptions and recommendation effectiveness from a recorded simulation', () => {
  const simulation = {
    n_infested_final: 2,
    request_payload: JSON.stringify({
      impact_assumptions: {
        yield_per_tree_kg: 45,
        farmgate_price_php_per_kg: 60,
        damage_base: 30,
      },
      dashboard_state: { treatment_efficacy: 0.75 },
    }),
  }

  assert.equal(economicInputsFromSimulation(simulation).recommendationEffectiveness, 0.75)
  assert.deepEqual(calculateSimulationEconomicImpact(simulation), {
    infested_count: 2,
    yield_per_tree_kg: 45,
    farmgate_price_php_per_kg: 60,
    damage_rate: 0.3,
    recommendation_effectiveness: 0.75,
    projected_loss: 1_620,
    estimated_savings: 1_215,
    remaining_loss: 405,
  })
})

test('uses explicit treatment efficacy and accepts percentage-form values', () => {
  const inputs = economicInputsFromSimulation({
    request_payload: {
      treatment_applications: [{ treatment_type: 'targeted_spray', efficacy: 80 }],
      dashboard_state: { treatment_efficacy: 0.5 },
    },
  })
  assert.equal(inputs.recommendationEffectiveness, 0.8)
  assert.equal(formatPhp(8400.4), 'PHP 8,400')
})

test('does not invent an estimate when the affected count was not recorded', () => {
  assert.equal(calculateSimulationEconomicImpact({}), null)
})
