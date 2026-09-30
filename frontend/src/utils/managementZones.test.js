import assert from 'node:assert/strict'
import test from 'node:test'

import {
  managementZonePayload,
  normalizeManagementZones,
  saveManagementZones,
} from './managementZones.js'
import {
  overlappingManagementZones,
  simplifyLassoCoordinates,
  treeIdsInPolygon,
} from './zoneSelection.js'

const ZONE = {
  id: 'zone-1',
  label: 'North Block',
  color: '#2563eb',
  coordinates: [[0, 0], [2, 0], [2, 2], [0, 2]],
  tree_count: 2,
}

test('management-zone payload keeps stable identity and drops display counts', () => {
  assert.deepEqual(managementZonePayload([ZONE]), [{
    id: 'zone-1',
    label: 'North Block',
    color: '#2563eb',
    coordinates: ZONE.coordinates,
  }])
})

test('failed management-zone save retains optimistic data for retry', async () => {
  const failed = await saveManagementZones('orchard-a', [ZONE], async () => {
    throw new Error('offline')
  })
  assert.equal(failed.ok, false)
  assert.equal(failed.message, 'offline')
  assert.equal(failed.zones[0].label, ZONE.label)
})

test('polygon and freehand selection return end-to-end tree membership', () => {
  const trees = [
    { tree_id: 'A', lon: 1, lat: 1 },
    { tree_id: 'B', lon: 3, lat: 1 },
  ]
  assert.deepEqual(treeIdsInPolygon(trees, ZONE.coordinates), ['A'])
  const raw = [[0, 0], [0.000001, 0], [1, 0], [1, 1], [0, 1]]
  assert.ok(simplifyLassoCoordinates(raw, 1).length < raw.length)
})

test('management zones report tree-level overlap clearly', () => {
  const trees = [{ tree_id: 'A', lon: 1, lat: 1 }]
  const candidate = { coordinates: [[0.5, 0.5], [1.5, 0.5], [1.5, 1.5], [0.5, 1.5]] }
  assert.deepEqual(overlappingManagementZones(candidate, [normalizeManagementZones([ZONE])[0]], trees).map((zone) => zone.id), ['zone-1'])
})
