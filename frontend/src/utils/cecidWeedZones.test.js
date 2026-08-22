import assert from 'node:assert/strict'
import test from 'node:test'

import {
  normalizeCecidWeedZones,
  saveCecidWeedZones,
  weedZonePayload,
} from './cecidWeedZones.js'

const ZONE = {
  id: 'weeds-a',
  label: 'Canal weeds',
  density: 'dense',
  coordinates: [[122.0, 10.0], [122.1, 10.0], [122.1, 10.1]],
  tree_count: 4,
}

test('weed zones normalize invalid density without losing polygon data', () => {
  const [zone] = normalizeCecidWeedZones([{ ...ZONE, density: 'high' }])
  assert.equal(zone.density, 'moderate')
  assert.deepEqual(zone.coordinates, ZONE.coordinates)
})

test('orchard payload excludes display-only tree counts', () => {
  assert.deepEqual(weedZonePayload([ZONE]), [{
    id: ZONE.id,
    label: ZONE.label,
    density: ZONE.density,
    coordinates: ZONE.coordinates,
  }])
})

test('failed save keeps optimistic zones available for retry', async () => {
  const failed = await saveCecidWeedZones('orchard-a', [ZONE], async () => {
    throw new Error('offline')
  })
  assert.equal(failed.ok, false)
  assert.equal(failed.message, 'offline')
  assert.deepEqual(failed.zones, [ZONE])

  let retryPayload
  const retried = await saveCecidWeedZones('orchard-a', failed.zones, async (_id, payload) => {
    retryPayload = payload
    return { data: { cecid_weed_zones: payload.cecid_weed_zones } }
  })
  assert.equal(retried.ok, true)
  assert.deepEqual(retryPayload.cecid_weed_zones, weedZonePayload([ZONE]))
  assert.equal(retried.zones[0].id, ZONE.id)
})
