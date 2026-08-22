import test from 'node:test'
import assert from 'node:assert/strict'
import {
  GUIMARAS_WONDERS_FARM_ID,
  GUIMARAS_WONDERS_FARM_OVERLAY_COORDINATES,
  mergeBundledOrchards,
} from './bundledOrchards.js'

const bundled = {
  orchard_id: GUIMARAS_WONDERS_FARM_ID,
  name: 'Guimaras Wonders Farm',
  geojson: {
    type: 'FeatureCollection',
    features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: [122.61, 10.63] } }],
  },
  orthophoto_coordinates: GUIMARAS_WONDERS_FARM_OVERLAY_COORDINATES,
}

test('bundled Guimaras Wonders Farm is present when the API omits it', () => {
  const orchards = mergeBundledOrchards([], bundled)
  assert.equal(orchards.length, 1)
  assert.equal(orchards[0].orchard_id, GUIMARAS_WONDERS_FARM_ID)
})

test('API orchard fields remain authoritative while missing map data is restored', () => {
  const orchards = mergeBundledOrchards([{
    orchard_id: GUIMARAS_WONDERS_FARM_ID,
    name: 'Server Farm Name',
    geojson: null,
    orthophoto_coordinates: null,
    monitoring_enabled: false,
  }], bundled)

  assert.equal(orchards.length, 1)
  assert.equal(orchards[0].name, 'Server Farm Name')
  assert.equal(orchards[0].monitoring_enabled, false)
  assert.equal(orchards[0].geojson.features.length, 1)
  assert.deepEqual(
    orchards[0].orthophoto_coordinates,
    GUIMARAS_WONDERS_FARM_OVERLAY_COORDINATES,
  )
})
