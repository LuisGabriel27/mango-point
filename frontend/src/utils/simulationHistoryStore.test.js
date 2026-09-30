import test from 'node:test'
import assert from 'node:assert/strict'

import {
  CURRENT_SIMULATION_MODEL_VERSION,
  buildReplayableSimulationRequest,
  normalizeSimulationRunForHistory,
} from './simulationHistoryStore.js'

test('frontend simulation model version matches the backend release', () => {
  assert.equal(CURRENT_SIMULATION_MODEL_VERSION, '2026.10-cecid-map-interpretation-v7')
})

test('generated simulation seed is copied into a replayable request', () => {
  const request = buildReplayableSimulationRequest(
    { pest_type: 'cecid', random_seed: null },
    { random_seed: 309463120 },
  )

  assert.equal(request.random_seed, 309463120)
})

test('an explicit simulation seed is never overwritten', () => {
  const request = buildReplayableSimulationRequest(
    { pest_type: 'cecid', random_seed: 42 },
    { random_seed: 309463120 },
  )

  assert.equal(request.random_seed, 42)
})

test('legacy forced Cecid source counts are not replayed', () => {
  const request = buildReplayableSimulationRequest({
    pest_type: 'cecid',
    random_seed: 42,
    cecid_assumed_source_count: 12,
  })

  assert.equal('cecid_assumed_source_count' in request, false)
})

test('browser history normalization repairs older null-seed records', () => {
  const detail = normalizeSimulationRunForHistory({
    run_id: 'sim-old',
    pest_type: 'cecid',
    random_seed: 1188526464,
    request_payload: { pest_type: 'cecid', random_seed: null },
  })

  assert.equal(detail.request_payload.random_seed, 1188526464)
  assert.equal(detail.input_parameters.random_seed, 1188526464)
})

test('model version is included without replacing saved dashboard controls', () => {
  const request = buildReplayableSimulationRequest(
    { dashboard_state: { sensitivity: 'standard' } },
    { metadata: { model_version: '2026.09-cecid-wind-v4' } },
  )

  assert.deepEqual(request.dashboard_state, {
    sensitivity: 'standard',
    simulation_model_version: '2026.09-cecid-wind-v4',
  })
})

test('effective tree graph distance is copied into a replayable request', () => {
  const request = buildReplayableSimulationRequest(
    { pest_type: 'fruitfly', simulation_mode: 'tree_graph' },
    {
      metadata: {
        model_version: CURRENT_SIMULATION_MODEL_VERSION,
        tg_max_neighbor_dist_m: 25,
      },
    },
  )

  assert.equal(request.tg_max_neighbor_dist_m, 25)
})

test('an explicit tree graph distance is never overwritten', () => {
  const request = buildReplayableSimulationRequest(
    {
      pest_type: 'fruitfly',
      simulation_mode: 'tree_graph',
      tg_max_neighbor_dist_m: 18,
    },
    {
      metadata: {
        model_version: CURRENT_SIMULATION_MODEL_VERSION,
        tg_max_neighbor_dist_m: 25,
      },
    },
  )

  assert.equal(request.tg_max_neighbor_dist_m, 18)
})

test('an old-model template adopts the current default graph distance', () => {
  const request = buildReplayableSimulationRequest(
    { pest_type: 'fruitfly', simulation_mode: 'tree_graph' },
    {
      metadata: {
        model_version: '2026.09-cecid-wind-v4',
        tg_max_neighbor_dist_m: 20,
      },
    },
  )

  assert.equal(request.tg_max_neighbor_dist_m, undefined)
})
