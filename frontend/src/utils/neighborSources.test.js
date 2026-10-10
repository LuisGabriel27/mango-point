import test from 'node:test'
import assert from 'node:assert/strict'
import { restoreNeighborSources, neighborPressureSummary, neighborRequestFields } from './neighborSources.js'
import { buildReplayableSimulationRequest } from './simulationHistoryStore.js'

test('old saved neighbor inputs restore as one source, preserving uniform pressure', () => {
  assert.deepEqual(restoreNeighborSources({ neighbor_threat: 0.4, neighbor_direction: 'E' }), [{ label: 'Neighbor 1', direction: 'E', threat: 0.4 }])
  assert.equal(restoreNeighborSources({ neighbor_threat: 0.4 })[0].direction, null)
  assert.deepEqual(restoreNeighborSources({ neighbor_sources: [], neighbor_threat: 1 }), [])
  assert.deepEqual(restoreNeighborSources({}), [])
})

test('multiple neighbors keep their individual pressures through request, history, and restoration', () => {
  const sources = [{ label: 'North farm', direction: 'N', threat: 0.6 }, { label: 'East farm', direction: 'E', threat: 0.7 }]
  const fields = neighborRequestFields(sources)
  assert.equal(fields.neighbor_threat, 1)
  assert.equal(fields.neighbor_direction, null)
  const replay = buildReplayableSimulationRequest(JSON.parse(JSON.stringify(fields)), { random_seed: 42 })
  assert.deepEqual(restoreNeighborSources(replay), sources)
  assert.equal(neighborPressureSummary(sources), 'N 60%, E 70%')
  assert.equal(neighborPressureSummary([]), 'No neighbor pressure')
})
