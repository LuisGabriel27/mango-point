import test from 'node:test'
import assert from 'node:assert/strict'

import { interpretCecidTree } from './cecidMapInterpretation.js'

test('likelihood mode uses repeated-run infestation frequency', () => {
  const result = interpretCecidTree({
    stage: 'fruitlet',
    state: 'unbagged',
    risk: 0.8,
    ensemble_runs: 5,
    ensemble_infestation_count: 2,
    ensemble_infestation_frequency: 0.4,
    cumulative_establishment_probability: 0.72,
    exposure_hours: 8,
  }, 'likelihood')

  assert.equal(result.displayRisk, 0.4)
  assert.equal(result.displayMode, 'likelihood')
  assert.equal(result.displayRiskLabel, 'Infestation frequency across runs')
  assert.equal(result.outcomeLabel, 'Established in 2 of 5 runs')
  assert.equal(result.eligible, true)
})

test('representative mode explains stochastic non-establishment after exposure', () => {
  const result = interpretCecidTree({
    stage: 'fruitlet',
    state: 'unbagged',
    risk: 0.2,
    exposure_hours: 4,
    exposure_route: 'local_soil_or_habitat',
  }, 'representative')

  assert.equal(result.displayRisk, 0.2)
  assert.match(result.explanation, /did not occur/)
  assert.match(result.exposureRouteLabel, /Local soil/)
})

test('non-fruitlet trees are identified as hard-gate ineligible', () => {
  const result = interpretCecidTree({ stage: 'mature', state: 'unbagged' })

  assert.equal(result.eligible, false)
  assert.match(result.explanation, /outside the Fruitlet hard gate/)
})

test('an established one-run score of 100% does not replace a yellow across-run frequency', () => {
  const properties = { stage: 'fruitlet', state: 'infested', risk: 1,
    ensemble_runs: 10, ensemble_infestation_count: 2, ensemble_infestation_frequency: 0.2 }
  const across = interpretCecidTree(properties, 'likelihood')
  const one = interpretCecidTree(properties, 'representative')
  assert.equal(across.displayRisk, 0.2)
  assert.equal(across.displayMode, 'likelihood')
  assert.equal(across.displayRiskLabel, 'Infestation frequency across runs')
  assert.equal(across.outcomeLabel, 'Established in 2 of 10 runs')
  assert.equal(one.displayRisk, 1)
  assert.equal(one.displayMode, 'representative')
  assert.equal(one.displayRiskLabel, 'One-run risk score')
  assert.match(one.displayExplanation, /does not mean 100% likelihood/)
})

test('missing repeated-run frequency falls back to a clearly labeled one-run score', () => {
  const result = interpretCecidTree({ stage: 'fruitlet', risk: 1,
    ensemble_runs: 10, ensemble_infestation_frequency: null }, 'likelihood')
  assert.equal(result.hasEnsemble, false)
  assert.equal(result.displayMode, 'representative')
  assert.equal(result.displayRisk, 1)
  assert.equal(result.displayRiskLabel, 'One-run risk score')
  assert.equal(result.cumulativeProbability, null)
  assert.equal(result.peakHourlyRisk, null)
})
