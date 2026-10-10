import test from 'node:test'
import assert from 'node:assert/strict'
import { buildRiskSurface, sampleRiskSurface, riskColor, riskSurfaceImage, applyRiskSurfaceCanvas, RISK_SURFACE_LAYER } from './riskSurface.js'

const lon = 122, lat = 10
const coordinate = (east = 0, north = 0) => [lon + east / (111195 * Math.cos(lat * Math.PI / 180)), lat + north / 111195]
const point = (east, risk, extra = {}, north = 0) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: coordinate(east, north) }, properties: { risk, ...extra } })
const fc = (...features) => ({ type: 'FeatureCollection', features })
const polygon = (west, south, east, north, risk) => ({ type: 'Feature', properties: { risk }, geometry: { type: 'Polygon', coordinates: [[coordinate(west, south), coordinate(east, south), coordinate(east, north), coordinate(west, north), coordinate(west, south)]] } })

function texelsAt(surface, position) {
  const [x, y] = surface.project.toLocal(position)
  const px = (x - surface.west) / (surface.east - surface.west) * surface.width - 0.5
  const py = (surface.north - y) / (surface.north - surface.south) * surface.height - 0.5
  return [Math.floor(py), Math.ceil(py)].flatMap((row) => [Math.floor(px), Math.ceil(px)].map((col) => row * surface.width + col))
}

test('isolated hotspots have broad smooth ground-distance halos in our existing palette', () => {
  const surface = buildRiskSurface(fc(point(0, 0.95)))
  assert.equal(sampleRiskSurface(surface, coordinate()).risk, 0.95)
  const near = sampleRiskSurface(surface, coordinate(8)).risk
  const far = sampleRiskSurface(surface, coordinate(18)).risk
  assert.ok(near > far && far > 0)
  assert.equal(sampleRiskSurface(surface, coordinate(50)).confidence, 0)
  assert.equal(RISK_SURFACE_LAYER.type, 'raster')
  assert.ok(!JSON.stringify(RISK_SURFACE_LAYER).includes('zoom'))
  assert.ok(!JSON.stringify(RISK_SURFACE_LAYER).includes('density'))
  assert.ok(surface.width > 100)
  assert.ok(surface.data.some((channel, index) => index % 4 === 3 && channel > 20 && channel < 230))
  assert.deepEqual([0, 0.1, 0.25, 0.5, 0.75, 1].map(riskColor), ['#22c55e', '#facc15', '#f59e0b', '#ef4444', '#b91c1c', '#b91c1c'])
})

test('every tree anchor and its bilinear texels keep their actual risk; zero-risk neighbors stay clear', () => {
  const input = fc(point(0, 0.95), point(7, 0), point(14, 0.25), point(21, 0.5), point(28, 0.75))
  const copy = structuredClone(input)
  const surface = buildRiskSurface(input)
  for (const tree of input.features) {
    const risk = tree.properties.risk
    assert.equal(sampleRiskSurface(surface, tree.geometry.coordinates).risk, risk)
    for (const index of texelsAt(surface, tree.geometry.coordinates)) {
      assert.ok(Math.abs(surface.values[index] - risk) < 1e-6)
      if (risk === 0) assert.equal(surface.data[index * 4 + 3], 0)
      else {
        const hex = '#' + [...surface.data.slice(index * 4, index * 4 + 3)].map((channel) => channel.toString(16).padStart(2, '0')).join('')
        assert.equal(hex, riskColor(risk))
      }
    }
  }
  assert.deepEqual(input, copy)
})

test('dense low-risk clusters cannot become high risk by point accumulation', () => {
  const trees = Array.from({ length: 12 }, (_, i) => point(i % 4 * 6, 0.2, {}, Math.floor(i / 4) * 6))
  const surface = buildRiskSurface(fc(...trees))
  assert.ok(Math.max(...surface.values) <= 0.200001)
  assert.ok(sampleRiskSurface(surface, coordinate(9, 9)).risk > 0.1)
})

test('low-risk halos stay green and zero controls survive very close trees or large extents', () => {
  const low = buildRiskSurface(fc(point(0, 0.08)))
  const [index] = texelsAt(low, coordinate(3))
  assert.deepEqual([...low.data.slice(index * 4, index * 4 + 3)], [34, 197, 94])
  for (const input of [fc(point(0, 1), point(0.2, 0)), fc(point(0, 0), point(4, 1), point(2500, 1))]) {
    const surface = buildRiskSurface(input)
    const zero = input.features.find((tree) => tree.properties.risk === 0)
    for (const pixel of texelsAt(surface, zero.geometry.coordinates)) {
      assert.equal(surface.values[pixel], 0)
      assert.equal(surface.data[pixel * 4 + 3], 0)
    }
  }
})

test('low-risk point controls stay green beside hot trees at close spacing or coarse resolution', () => {
  for (const input of [fc(point(0, 1), point(0.2, 0.05)), fc(point(0, 0.05), point(4, 1), point(10000, 1))]) {
    const surface = buildRiskSurface(input)
    const low = input.features.find((tree) => tree.properties.risk === 0.05)
    for (const pixel of texelsAt(surface, low.geometry.coordinates)) {
      assert.ok(Math.abs(surface.values[pixel] - 0.05) < 1e-6)
      assert.deepEqual([...surface.data.slice(pixel * 4, pixel * 4 + 4)], [34, 197, 94, 255])
    }
  }
})

test('ground coordinates, bandwidth and resolution stay identical when only simulation values change', () => {
  const a = buildRiskSurface(fc(point(0, 0.2), point(10, 0.3)))
  const b = buildRiskSurface(fc(point(0, 0.9), point(10, 0.8)))
  assert.deepEqual(a.coordinates, b.coordinates)
  assert.equal(a.width, b.width)
  assert.equal(a.height, b.height)
  assert.equal(a.sigmaM, b.sigmaM)
  const [[west, north], [east], [, south]] = a.coordinates
  assert.ok(west < east && north > south)
})

test('Cecid likelihood and representative maps use the selected simulation value', () => {
  const tree = point(0, 0.8, { stage: 'fruitlet', ensemble_runs: 5, ensemble_infestation_frequency: 0.2 })
  assert.equal(sampleRiskSurface(buildRiskSurface(fc(tree), 'cecid', 'representative'), coordinate()).risk, 0.8)
  assert.equal(sampleRiskSurface(buildRiskSurface(fc(tree), 'cecid', 'likelihood'), coordinate()).risk, 0.2)
  const surface = buildRiskSurface(fc(tree, point(7, 1, { stage: 'mature' })), 'cecid')
  assert.equal(sampleRiskSurface(surface, coordinate(7)).risk, 0)
  const established = point(0, 1, { stage: 'fruitlet', state: 'infested', ensemble_runs: 10,
    ensemble_infestation_count: 2, ensemble_infestation_frequency: 0.2 })
  const across = buildRiskSurface(fc(established), 'cecid', 'likelihood')
  const one = buildRiskSurface(fc(established), 'cecid', 'representative')
  for (const pixel of texelsAt(across, coordinate())) {
    assert.deepEqual([...across.data.slice(pixel * 4, pixel * 4 + 3)], [250, 204, 21])
  }
  for (const pixel of texelsAt(one, coordinate())) {
    assert.deepEqual([...one.data.slice(pixel * 4, pixel * 4 + 3)], [185, 28, 28])
  }
})

test('dead, missing-risk and ineligible controls prevent hot halos at their own location', () => {
  const input = fc(point(0, 1), point(7, 1, { state: 'dead' }), point(14, null), point(21, undefined))
  const surface = buildRiskSurface(input)
  for (const tree of input.features.slice(1)) {
    assert.equal(sampleRiskSurface(surface, tree.geometry.coordinates).risk, 0)
    for (const index of texelsAt(surface, tree.geometry.coordinates)) assert.equal(surface.data[index * 4 + 3], 0)
  }
  assert.equal(buildRiskSurface(null), null)
  assert.equal(buildRiskSurface(fc(point(0, 0))), null)
  assert.equal(buildRiskSurface(fc(point(0, NaN))), null)
  assert.equal(buildRiskSurface(fc({ ...point(0, 1), geometry: { type: 'Point', coordinates: [NaN, 10] } })), null)
})

test('Fruit Fly ensemble heat uses frequency while one-run heat and reservoir status stay independent', () => {
  const tree = point(0, 1, { state: 'infested', ensemble_runs: 9,
    ensemble_infestation_count: 2, ensemble_infestation_frequency: 2 / 9 })
  const across = buildRiskSurface(fc(tree), 'fruitfly', 'likelihood')
  const one = buildRiskSurface(fc(tree), 'fruitfly', 'representative')
  assert.equal(sampleRiskSurface(across, coordinate()).risk, 2 / 9)
  assert.equal(sampleRiskSurface(one, coordinate()).risk, 1)
  assert.deepEqual(across.coordinates, one.coordinates)
  for (const pixel of texelsAt(across, coordinate())) {
    assert.deepEqual([...across.data.slice(pixel * 4, pixel * 4 + 3)], [250, 204, 21])
  }
  const reservoir = point(0, 0.12, { state: 'unbagged', initial_source: true,
    initial_source_assumed: true, initial_source_origin: 'history_reservoir' })
  assert.equal(sampleRiskSurface(buildRiskSurface(fc(reservoir)), coordinate()).risk, 0.12)
})

test('resolved marker overrides drive the same surface state and risk', () => {
  const input = fc(point(0, 1), point(7, 1))
  const displayed = [
    { lon, lat, display_risk: 0.4, status: 'healthy', geometry: input.features[0].geometry },
    { lon: coordinate(7)[0], lat, display_risk: 1, status: 'dead', geometry: input.features[1].geometry },
  ]
  const surface = buildRiskSurface(input, 'fruitfly', 'representative', displayed)
  assert.equal(sampleRiskSurface(surface, coordinate()).risk, 0.4)
  assert.equal(sampleRiskSurface(surface, coordinate(7)).risk, 0)
})

test('grid polygons keep exact values including zero cells and holes', () => {
  const hot = polygon(-2.5, -2.5, 2.5, 2.5, 0.9)
  const clear = polygon(2.5, -2.5, 7.5, 2.5, 0)
  const surface = buildRiskSurface(fc(hot, clear))
  assert.equal(sampleRiskSurface(surface, coordinate(2, 2)).risk, 0.9)
  assert.equal(sampleRiskSurface(surface, coordinate(6, 1)).risk, 0)
  assert.ok(sampleRiskSurface(surface, coordinate(-8)).risk > 0)
  const hole = polygon(-1, -1, 1, 1, 0)
  hot.geometry.coordinates.push(hole.geometry.coordinates[0])
  assert.equal(sampleRiskSurface(buildRiskSurface(fc(hot)), coordinate()).risk, 0)
})

test('coincident samples deduplicate without density inflation and conflicts stay clear', () => {
  const identical = buildRiskSurface(fc(point(0, 0.3), point(0, 0.3)))
  assert.equal(identical.samples.length, 1)
  assert.equal(sampleRiskSurface(identical, coordinate()).risk, 0.3)
  const conflict = buildRiskSurface(fc(point(0, 1), point(0, 0), point(10, 0.8)))
  assert.equal(sampleRiskSurface(conflict, coordinate()).risk, 0)
})

test('a MultiPolygon island inside a hole retains its valid risk', () => {
  const outer = polygon(-5, -5, 5, 5, 0.8)
  outer.geometry.coordinates.push(polygon(-3, -3, 3, 3, 0).geometry.coordinates[0])
  const island = polygon(-1, -1, 1, 1, 0.8)
  const feature = { ...outer, geometry: { type: 'MultiPolygon', coordinates: [outer.geometry.coordinates, island.geometry.coordinates] } }
  const surface = buildRiskSurface(fc(feature))
  assert.equal(sampleRiskSurface(surface, coordinate()).risk, 0.8)
  assert.equal(sampleRiskSurface(surface, coordinate(2)).risk, 0)
})

test('raster image generation preserves RGBA data for standalone export', () => {
  const surface = buildRiskSurface(fc(point(0, 0.9)))
  let pixels, imageType
  const canvas = { getContext: () => ({
    createImageData: (width, height) => ({ data: new Uint8ClampedArray(width * height * 4) }),
    putImageData: (image) => { pixels = image.data },
  }), toDataURL: (type) => { imageType = type; return 'data:image/png;base64,AAAA' } }
  assert.equal(riskSurfaceImage(surface, () => canvas), 'data:image/png;base64,AAAA')
  assert.equal(imageType, 'image/png')
  assert.deepEqual(pixels, surface.data)
})

test('playback retains one canvas and uploads each latest frame without image fetches', () => {
  let pixels, uploaded, playing = false, coordinateChanges = 0, sourceAdds = 0
  const canvas = { getContext: () => ({
    createImageData: (width, height) => ({ data: new Uint8ClampedArray(width * height * 4) }),
    putImageData: (image) => { pixels = new Uint8ClampedArray(image.data) },
    clearRect: () => pixels.fill(0),
  }) }
  const layers = [{ id: 'ortho-layer' }, { id: 'stage-zones-fill' }], sources = new Map()
  const map = {
    getLayer: (id) => layers.find((layer) => layer.id === id),
    getSource: (id) => sources.get(id),
    getStyle: () => ({ layers }),
    removeLayer: (id) => layers.splice(layers.findIndex((layer) => layer.id === id), 1),
    removeSource: (id) => sources.delete(id),
    addSource: (id, options) => {
      assert.equal(options.type, 'canvas')
      assert.equal(options.animate, false)
      sourceAdds += 1
      sources.set(id, { ...options, getCanvas: () => options.canvas,
        setCoordinates: function (coordinates) { coordinateChanges += 1; this.coordinates = coordinates },
        play: () => { playing = true },
        pause: () => { if (playing) uploaded = new Uint8ClampedArray(pixels); playing = false },
      })
    },
    addLayer: (layer, before) => layers.splice(layers.findIndex((item) => item.id === before), 0, layer),
    setLayoutProperty: (id, property, value) => {
      const layer = layers.find((item) => item.id === id)
      layer.layout = { ...layer.layout, [property]: value }
    },
    triggerRepaint: () => {},
  }
  const first = buildRiskSurface(fc(point(0, 0.9), point(10, 0)))
  applyRiskSurfaceCanvas(map, first, () => canvas)
  assert.deepEqual(layers.map((layer) => layer.id), ['ortho-layer', 'risk-heatmap', 'stage-zones-fill'])
  const retained = sources.get('risk-heatmap-src')
  assert.deepEqual(uploaded, first.data)
  for (const input of [fc(point(0, 0.3), point(10, 0.1)), fc(point(0, 0), point(10, 1))]) {
    const frame = buildRiskSurface(input)
    applyRiskSurfaceCanvas(map, frame)
    assert.equal(sources.get('risk-heatmap-src'), retained)
    assert.equal(retained.getCanvas(), canvas)
    assert.deepEqual(uploaded, frame.data)
    assert.equal(playing, false)
  }
  assert.equal(sourceAdds, 1)
  assert.equal(coordinateChanges, 0)
  assert.equal(layers.filter((layer) => layer.id === 'risk-heatmap').length, 1)
  applyRiskSurfaceCanvas(map, null)
  assert.equal(sources.get('risk-heatmap-src'), retained)
  assert.equal(map.getLayer('risk-heatmap').layout.visibility, 'none')
  assert.ok(uploaded.every((value) => value === 0))
  const moved = buildRiskSurface(fc(point(80, 1)))
  applyRiskSurfaceCanvas(map, moved)
  assert.equal(coordinateChanges, 1)
  assert.equal(map.getLayer('risk-heatmap').layout.visibility, 'visible')
  assert.deepEqual(uploaded, moved.data)
  assert.deepEqual(retained.coordinates, moved.coordinates)
})
