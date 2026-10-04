import test from 'node:test'
import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import { runWhenMapReady } from './mapReady.js'

function createMap() {
  const map = new EventEmitter()
  map.hasLoaded = false
  map.busy = false
  map.loaded = () => map.hasLoaded && !map.busy
  map.finishRender = () => {
    map.busy = false
    if (!map.hasLoaded) {
      map.hasLoaded = true
      map.emit('load')
    }
  }
  const sources = new Map()
  map.getSource = (id) => {
    if (!sources.has(id)) {
      sources.set(id, {
        data: null,
        setData(data) {
          this.data = data
          map.busy = true
        },
      })
    }
    return sources.get(id)
  }
  return map
}

const EMPTY_ZONES = { type: 'FeatureCollection', features: [] }
const STATUS_ZONE = {
  type: 'FeatureCollection',
  features: [{
    type: 'Feature',
    properties: { status: 'infected' },
    geometry: { type: 'Polygon', coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]]] },
  }],
}

test('clearing status zones and a draft removes both while the map is rendering', () => {
  const map = createMap()
  map.finishRender()
  const zones = map.getSource('status-zones-src')
  const draft = map.getSource('status-zone-draft-src')
  zones.setData(STATUS_ZONE)
  draft.setData(STATUS_ZONE)
  assert.equal(map.loaded(), false)

  runWhenMapReady(map, map.hasLoaded, () => {
    zones.setData(EMPTY_ZONES)
    draft.setData(EMPTY_ZONES)
  })
  map.finishRender()

  assert.deepEqual(zones.data.features, [])
  assert.deepEqual(draft.data.features, [])
  assert.equal(map.listenerCount('load'), 0)
})

test('consecutive zone edits apply the latest boundary before the next render', () => {
  const map = createMap()
  map.finishRender()
  const source = map.getSource('status-zones-src')
  runWhenMapReady(map, map.hasLoaded, () => source.setData(STATUS_ZONE))
  const updatedZone = structuredClone(STATUS_ZONE)
  updatedZone.features[0].geometry.coordinates[0][1] = [2, 0]
  runWhenMapReady(map, map.hasLoaded, () => source.setData(updatedZone))

  assert.deepEqual(source.data, updatedZone)
})

test('clearing zones before initial load cancels the pending stale drawing', () => {
  const map = createMap()
  const source = map.getSource('status-zones-src')
  const cancelStaleUpdate = runWhenMapReady(map, map.hasLoaded, () => source.setData(STATUS_ZONE))
  assert.equal(source.data, null)

  cancelStaleUpdate()
  runWhenMapReady(map, map.hasLoaded, () => source.setData(EMPTY_ZONES))
  map.finishRender()

  assert.deepEqual(source.data.features, [])
  assert.equal(map.listenerCount('load'), 0)
})

test('unmounting before initial load cancels the pending map update', () => {
  const map = createMap()
  let updated = false
  const cleanup = runWhenMapReady(map, map.hasLoaded, () => { updated = true })
  cleanup()
  map.finishRender()

  assert.equal(updated, false)
  assert.equal(map.listenerCount('load'), 0)
})
