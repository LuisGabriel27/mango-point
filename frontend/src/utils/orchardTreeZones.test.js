import test from 'node:test'
import assert from 'node:assert/strict'
import {
  normalizeStageZones,
  normalizeStatusZones,
  stageZonePayload,
  statusZonePayload,
} from './orchardTreeZones.js'

const POLYGON = [[122, 10], [122.1, 10], [122.1, 10.1]]

test('stored orchard zones reload with orchard scope', () => {
  const stages = normalizeStageZones([{ id: 's1', stage: 'fruitlet', coordinates: POLYGON }], 'orchard')
  const statuses = normalizeStatusZones(JSON.stringify([
    { id: 't1', status: 'suspect', coordinates: POLYGON },
  ]), 'orchard')
  assert.equal(stages[0].scope, 'orchard')
  assert.equal(statuses[0].scope, 'orchard')
})

test('only apply-to-orchard zones are sent to persistent storage', () => {
  const stages = [
    { id: 'temporary', stage: 'mature', coordinates: POLYGON, scope: 'scenario' },
    { id: 'saved', stage: 'fruitlet', coordinates: POLYGON, scope: 'orchard', tree_count: 3 },
  ]
  const statuses = [
    { id: 'temporary-status', status: 'infected', coordinates: POLYGON, scope: 'scenario' },
    { id: 'saved-status', status: 'suspect', coordinates: POLYGON, scope: 'orchard' },
  ]
  assert.deepEqual(stageZonePayload(stages), [
    { id: 'saved', stage: 'fruitlet', coordinates: POLYGON },
  ])
  assert.deepEqual(statusZonePayload(statuses), [
    { id: 'saved-status', status: 'suspect', coordinates: POLYGON },
  ])
})

test('scenario is the default scope and invalid zone settings are dropped', () => {
  assert.equal(normalizeStageZones([{ id: 's1', stage: 'mature', coordinates: POLYGON }])[0].scope, 'scenario')
  assert.deepEqual(normalizeStatusZones([{ id: 'bad', status: 'unknown', coordinates: POLYGON }]), [])
})

