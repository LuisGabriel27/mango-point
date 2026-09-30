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

