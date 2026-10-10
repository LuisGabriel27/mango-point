import test from 'node:test'
import assert from 'node:assert/strict'
import {
  initialSourceDetails, interpretSimulationTree, resolveTreeStatuses,
  selectableTreeStatus, simulationEnsembleRuns, simulationUncertaintySummary,
} from './simulationMapInterpretation.js'

test('Fruit Fly across-runs frequency stays distinct from an infested one-run score', () => {
  const properties = { state: 'infested', risk: 1, ensemble_runs: 9,
    ensemble_infestation_count: 2, ensemble_infestation_frequency: 2 / 9 }
  const across = interpretSimulationTree(properties, 'likelihood')
  const one = interpretSimulationTree(properties, 'representative')
  assert.equal(across.displayRisk, 2 / 9)
  assert.equal(across.outcomeLabel, 'Infested in 2 of 9 runs')
  assert.equal(one.displayRisk, 1)
  assert.equal(one.representativeEstablished, true)
  assert.match(one.displayExplanation, /does not mean 100% likelihood/)
})

test('missing ensemble evidence falls back to a labeled one-run result', () => {
  const result = interpretSimulationTree({ risk: 0.3, ensemble_runs: 5,
    ensemble_infestation_frequency: null }, 'likelihood')
  assert.equal(result.displayMode, 'representative')
  assert.equal(result.displayRisk, 0.3)
  assert.equal(result.displayRiskLabel, 'One-run risk score')
})

test('recorded Suspect or History inputs cannot hide a simulated infestation', () => {
  for (const input of ['suspect', 'history_infected']) {
    const { inputStatus, status } = resolveTreeStatuses({ state: 'infested', risk: 1 }, input)
    assert.equal(inputStatus, input)
    assert.equal(status, 'infested')
    assert.equal(interpretSimulationTree({ state: status, risk: 1 }, 'representative').representativeEstablished, true)
  }
  assert.equal(selectableTreeStatus('infested'), 'infected')
  assert.equal(selectableTreeStatus('unbagged'), 'healthy')
  assert.deepEqual(resolveTreeStatuses({ Status: 'History Infected' }), {
    inputStatus: 'history_infected', status: 'history_infected',
  })
})

test('an assumed historical reservoir has its own badge without forcing fruit infestation', () => {
  const properties = { state: 'unbagged', risk: 0.12, initial_source: true,
    initial_source_assumed: true, initial_source_origin: 'history_reservoir',
    initial_source_label: 'Possible historical adult reservoir' }
  const source = initialSourceDetails(properties, 'fruitfly')
  assert.equal(source.badge, 'R')
  assert.equal(source.assumed, true)
  assert.match(source.label, /reservoir/)
  const result = interpretSimulationTree(properties, 'representative')
  assert.equal(result.displayRisk, 0.12)
  assert.equal(result.representativeEstablished, false)
  assert.equal(initialSourceDetails({ ...properties, initial_source: false }), null)
  assert.equal(initialSourceDetails({ ...properties, initial_source_origin: 'suspect_infection' }).badge, 'S')
})

test('generic ensemble summaries take precedence while saved Cecid aliases remain readable', () => {
  const generic = { runs: 9, minimum: 1, maximum: 4 }
  const legacy = { runs: 5, minimum: 0, maximum: 3 }
  assert.equal(simulationUncertaintySummary({ metadata: { uncertainty_summary: generic,
    cecid_uncertainty_summary: legacy } }), generic)
  assert.equal(simulationUncertaintySummary({ metadata: { cecid_uncertainty_summary: legacy } }), legacy)
  assert.equal(simulationEnsembleRuns({ risk_geojson: { features: [{ properties: { ensemble_runs: 5 } }] } }), 5)
})
