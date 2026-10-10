import test from 'node:test'
import assert from 'node:assert/strict'
import { sourcePresenceOverrides, sourceProbability } from './sourcePresence.js'
import { normalizeStatusZones, statusZonePayload, mergeStoredStatusZones } from './orchardTreeZones.js'
import { buildZoneInventory } from './zoneInventory.js'

const coordinates = [[0, 0], [3, 0], [3, 3], [0, 3]]
const points = [
  { tree_id: 'a', lon: 1, lat: 1, status: 'healthy' },
  { tree_id: 'b', lon: 2, lat: 2, status: 'healthy' },
  { tree_id: 'outside', lon: 5, lat: 5, status: 'suspect' },
]
const zone = { id: 'z', status: 'suspect', source_probability: 0.7, coordinates, scope: 'orchard' }

test('zone percentages apply only inside the polygon; individual settings override them', () => {
  assert.deepEqual(sourcePresenceOverrides([zone], points), { a: 0.7, b: 0.7 })
  assert.deepEqual(sourcePresenceOverrides([zone], points, {}, { a: 0.2, outside: 0.8 }),
    { a: 0.2, b: 0.7, outside: 0.8 })
  assert.deepEqual(sourcePresenceOverrides([zone], points, {}, { a: null }), { b: 0.7 })
})

test('the last zone controls overlaps including an explicit return to scenario defaults', () => {
  const later = { ...zone, id: 'later', status: 'history_infected', source_probability: 0 }
  assert.deepEqual(sourcePresenceOverrides([zone, later], points), { a: 0, b: 0 })
  assert.deepEqual(sourcePresenceOverrides([zone, { ...later, source_probability: null }], points), {})
  assert.deepEqual(sourcePresenceOverrides([zone, { ...later, status: 'infected' }], points), {})
})

test('status edits prevent an old zone probability applying to the wrong source type', () => {
  assert.deepEqual(sourcePresenceOverrides([zone], points, { a: 'healthy', b: 'infected' }), {})
  assert.deepEqual(sourcePresenceOverrides([zone], points, { a: 'history_infected' }, { a: 1 }), { a: 1, b: 0.7 })
  assert.deepEqual(sourcePresenceOverrides([zone], points, { a: 'history_infected' }), { b: 0.7 })
})

test('source probability accepts endpoints and rejects missing or invalid values', () => {
  for (const value of [null, undefined, '', ' ', true, NaN, Infinity, -0.1, 1.1]) assert.equal(sourceProbability(value), null)
  assert.equal(sourceProbability(0), 0)
  assert.equal(sourceProbability(1), 1)
})

test('zone percentages survive persistence and replay, and appear in zone records', () => {
  for (const probability of [0, 0.7, 1]) {
    const saved = statusZonePayload([{ ...zone, source_probability: probability }])
    const restored = normalizeStatusZones(JSON.stringify(saved), 'orchard')
    assert.equal(restored[0].source_probability, probability)
    assert.deepEqual(sourcePresenceOverrides(restored, points), { a: probability, b: probability })
    assert.match(buildZoneInventory({ statusZones: restored })[0].detail,
      new RegExp(`${Math.round(probability * 100)}% source presence`))
  }
  const infected = statusZonePayload([{ ...zone, status: 'infected' }])
  assert.equal(Object.hasOwn(infected[0], 'source_probability'), false)
})

test('refreshing orchard zones preserves overlap order and removes deleted saved zones', () => {
  const scenario = { ...zone, id: 'scenario', scope: 'scenario', source_probability: 0.2 }
  const merged = mergeStoredStatusZones([zone, scenario], [{ ...zone, source_probability: 0.9 }])
  assert.deepEqual(merged.map((z) => z.id), ['z', 'scenario'])
  assert.deepEqual(sourcePresenceOverrides(merged, points), { a: 0.2, b: 0.2 })
  assert.deepEqual(mergeStoredStatusZones([zone, scenario], []), [scenario])
  assert.deepEqual(mergeStoredStatusZones([zone, scenario], [zone], true), [zone])
})
