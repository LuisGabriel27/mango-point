import { interpretCecidTree } from './cecidMapInterpretation.js'
import { interpretSimulationTree } from './simulationMapInterpretation.js'
import { geometryCenter } from './mapGeometry.js'
import { pointInPolygon } from './zoneSelection.js'

export const RISK_LEGEND_ENTRIES = [
  { label: 'Critical: 75–100%', color: '#b91c1c' },
  { label: 'Severe: 50–<75%', color: '#ef4444' },
  { label: 'High: 25–<50%', color: '#f59e0b' },
  { label: 'Moderate: 10–<25%', color: '#facc15' },
  { label: 'Low: <10%', color: '#22c55e' },
]

export function riskColor(risk) {
  if (risk == null || !Number.isFinite(risk)) return null
  if (risk >= 0.75) return '#b91c1c'
  if (risk >= 0.5) return '#ef4444'
  if (risk >= 0.25) return '#f59e0b'
  if (risk >= 0.1) return '#facc15'
  return '#22c55e'
}

export const RISK_SURFACE_LAYER = {
  id: 'risk-heatmap',
  type: 'raster',
  source: 'risk-heatmap-src',
  paint: { 'raster-opacity': 0.82, 'raster-fade-duration': 0, 'raster-resampling': 'linear' },
}

const EARTH_RADIUS = 6371008.8
const RAD = Math.PI / 180
const rgb = (hex) => [1, 3, 5].map((offset) => Number.parseInt(hex.slice(offset, offset + 2), 16))
const COLOR_STOPS = [
  [0, rgb('#22c55e')], [0.09, rgb('#22c55e')], [0.1, rgb('#facc15')],
  [0.225, rgb('#facc15')], [0.25, rgb('#f59e0b')],
  [0.45, rgb('#f59e0b')], [0.5, rgb('#ef4444')],
  [0.7, rgb('#ef4444')], [0.75, rgb('#b91c1c')], [1, rgb('#b91c1c')],
]

function gradientColor(risk) {
  for (let index = 1; index < COLOR_STOPS.length; index += 1) {
    const [end, right] = COLOR_STOPS[index]
    if (risk > end) continue
    const [start, left] = COLOR_STOPS[index - 1]
    const fraction = Math.max(0, (risk - start) / (end - start))
    return left.map((channel, i) => Math.round(channel + (right[i] - channel) * fraction))
  }
  return COLOR_STOPS.at(-1)[1]
}

function validCoordinate(coordinate) {
  return Array.isArray(coordinate) && coordinate.length >= 2
    && coordinate.slice(0, 2).every(Number.isFinite) && Math.abs(coordinate[0]) <= 180 && Math.abs(coordinate[1]) < 85
}

function projection(center) {
  // An affine Mercator grid maps exactly to MapLibre's image-source rectangle.
  // Scale to ground meters at the orchard latitude instead of screen pixels.
  const scale = Math.cos(center[1] * RAD)
  const originX = EARTH_RADIUS * center[0] * RAD
  const originY = EARTH_RADIUS * Math.log(Math.tan(Math.PI / 4 + center[1] * RAD / 2))
  return {
    toLocal: ([lon, lat]) => [
      (EARTH_RADIUS * lon * RAD - originX) * scale,
      (EARTH_RADIUS * Math.log(Math.tan(Math.PI / 4 + lat * RAD / 2)) - originY) * scale,
    ],
    toCoordinate: ([x, y]) => [
      (originX + x / scale) / EARTH_RADIUS / RAD,
      (2 * Math.atan(Math.exp((originY + y / scale) / EARTH_RADIUS)) - Math.PI / 2) / RAD,
    ],
  }
}

function polygonRings(geometry, project) {
  const polygons = geometry?.type === 'Polygon' ? [geometry.coordinates]
    : geometry?.type === 'MultiPolygon' ? (geometry.coordinates || []) : []
  return polygons.filter(Array.isArray).map((polygon) => (
    polygon.filter(Array.isArray).map((ring) => ring.filter(validCoordinate).map(project))
  )).filter((polygon) => polygon[0]?.length >= 3)
}

function rawSamples(geojson, pestType, mode, displayedPoints) {
  if (displayedPoints) return displayedPoints.map((point) => ({
    coordinate: [point.lon, point.lat], geometry: point.geometry,
    risk: point.display_risk, blocked: point.status === 'dead' || point.cecid?.eligible === false,
  }))
  return (geojson?.features || []).flatMap((feature) => {
    const coordinate = geometryCenter(feature.geometry)
    if (!validCoordinate(coordinate)) return []
    const props = feature.properties || {}
    const interpreted = pestType === 'cecid' ? interpretCecidTree(props, mode) : interpretSimulationTree(props, mode)
    return [{ coordinate, geometry: feature.geometry,
      risk: interpreted.displayRisk,
      blocked: ['dead', 'empty'].includes(String(props.state ?? props.status ?? props.Status).toLowerCase()) || interpreted?.eligible === false,
    }]
  })
}

function bucketKey(x, y, size) {
  return Math.floor(x / size) + ',' + Math.floor(y / size)
}

function addBucket(buckets, key, sample) {
  if (!buckets.has(key)) buckets.set(key, [])
  buckets.get(key).push(sample)
}

function surfaceSample(surface, x, y) {
  const { supportM, sigmaM, buckets, areaBuckets } = surface
  // Grid-cell values remain exact throughout their area, including zeros and
  // polygon holes. Smooth interpolation fills only the space between them.
  let inHole = false
  for (const sample of areaBuckets.get(bucketKey(x, y, supportM)) || []) {
    for (const polygon of sample.polygons) {
      if (!pointInPolygon([x, y], polygon[0])) continue
      if (polygon.slice(1).some((hole) => pointInPolygon([x, y], hole))) { inHole = true; continue }
      return { risk: sample.risk, confidence: sample.risk > 0 ? 1 : 0, anchor: true }
    }
  }
  if (inHole) return { risk: 0, confidence: 0, anchor: true }
  const col = Math.floor(x / supportM), row = Math.floor(y / supportM)
  let total = 0, weighted = 0, confidence = 0
  let nearest = null, nearestDistance = Infinity
  for (let dy = -1; dy <= 1; dy += 1) {
    for (let dx = -1; dx <= 1; dx += 1) {
      for (const sample of buckets.get((col + dx) + ',' + (row + dy)) || []) {
        const distance = Math.hypot(x - sample.x, y - sample.y)
        if (distance > supportM) continue
        if (distance < nearestDistance) { nearest = sample; nearestDistance = distance }
        const outsideCore = Math.max(0, distance - sample.anchorM)
        const falloff = Math.exp(-0.5 * (outsideCore / sigmaM) ** 2)
        const edgeFade = Math.max(0, Math.min(1, (supportM - distance) / sigmaM))
        const envelope = falloff * edgeFade
        const weight = envelope / Math.max(0.01, outsideCore ** 2)
        weighted += weight * sample.risk
        total += weight
        confidence = Math.max(confidence, envelope)
      }
    }
  }
  if (!nearest || total <= 0) return { risk: 0, confidence: 0, anchor: false }
  if (nearestDistance <= nearest.anchorM) return { risk: nearest.risk, confidence: nearest.risk > 0 ? 1 : 0, anchor: true }
  // Normalize weights so dense clusters cannot inflate the modeled risk.
  // The fixed ground-distance envelope makes isolated hotspots soften outward.
  return { risk: Math.max(0, Math.min(1, weighted / total * confidence)), confidence, anchor: false }
}

export function buildRiskSurface(geojson, pestType = 'fruitfly', mode = 'representative', displayedPoints = null) {
  const raw = rawSamples(geojson, pestType, mode, displayedPoints).filter((sample) => validCoordinate(sample.coordinate))
  if (!raw.some((sample) => !sample.blocked && Number.isFinite(Number(sample.risk)) && Number(sample.risk) > 0)) return null
  const project = projection(raw[0].coordinate)
  const unique = new Map()
  for (const item of raw) {
    const [x, y] = project.toLocal(item.coordinate)
    const hasRisk = item.risk != null && item.risk !== '' && Number.isFinite(Number(item.risk))
    const risk = item.blocked || !hasRisk ? 0 : Math.max(0, Math.min(1, Number(item.risk)))
    const key = x.toFixed(4) + ',' + y.toFixed(4)
    const previous = unique.get(key)
    if (previous) {
      // Contradictory duplicates cannot truthfully display both risks.
      if (previous.risk !== risk) previous.risk = 0
      continue
    }
    unique.set(key, { x, y, risk, polygons: polygonRings(item.geometry, project.toLocal), anchorM: 2 })
  }
  const samples = [...unique.values()]
  const nearest = samples.map((sample, i) => {
    let distance = Infinity
    for (let j = 0; j < samples.length; j += 1) {
      if (i !== j) distance = Math.min(distance, Math.hypot(sample.x - samples[j].x, sample.y - samples[j].y))
    }
    sample.anchorM = Math.min(2, distance * 0.4)
    return distance
  }).filter(Number.isFinite).sort((a, b) => a - b)
  const sigmaM = Math.max(8, Math.min(16, (nearest[Math.floor(nearest.length / 2)] || 12) * 0.9))
  const supportM = sigmaM * 3
  const buckets = new Map(), areaBuckets = new Map()
  let west = Infinity, east = -Infinity, south = Infinity, north = -Infinity
  for (const sample of samples) {
    addBucket(buckets, bucketKey(sample.x, sample.y, supportM), sample)
    const vertices = sample.polygons.flat(2)
    const xs = [sample.x, ...vertices.map((coordinate) => coordinate[0])]
    const ys = [sample.y, ...vertices.map((coordinate) => coordinate[1])]
    const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys)
    west = Math.min(west, minX - supportM); east = Math.max(east, maxX + supportM)
    south = Math.min(south, minY - supportM); north = Math.max(north, maxY + supportM)
    if (sample.polygons.length) {
      for (let row = Math.floor(minY / supportM); row <= Math.floor(maxY / supportM); row += 1) {
        for (let col = Math.floor(minX / supportM); col <= Math.floor(maxX / supportM); col += 1) {
          addBucket(areaBuckets, col + ',' + row, sample)
        }
      }
    }
  }
  const metersPerPixel = Math.max(0.5, (east - west) / 2048, (north - south) / 2048)
  const width = Math.max(2, Math.ceil((east - west) / metersPerPixel))
  const height = Math.max(2, Math.ceil((north - south) / metersPerPixel))
  const surface = { width, height, west, east, south, north, sigmaM, supportM, buckets, areaBuckets, project,
    coordinates: [[west, north], [east, north], [east, south], [west, south]].map(project.toCoordinate),
    samples, data: new Uint8ClampedArray(width * height * 4), values: new Float32Array(width * height),
  }
  for (let row = 0; row < height; row += 1) {
    const y = north - (row + 0.5) / height * (north - south)
    for (let col = 0; col < width; col += 1) {
      const x = west + (col + 0.5) / width * (east - west)
      const result = surfaceSample(surface, x, y)
      const index = row * width + col
      surface.values[index] = result.risk
      if (result.risk <= 0 || result.confidence <= 0) continue
      const color = result.anchor ? rgb(riskColor(result.risk)) : gradientColor(result.risk)
      surface.data.set([...color, Math.round(255 * result.confidence)], index * 4)
    }
  }
  // Preserve each point's risk in all four GPU bilinear contributors, even
  // with sub-meter spacing or coarse pixels. Lower-risk controls win shared
  // texels conservatively; zero controls clear them last. Polygon membership
  // remains authoritative so centers in holes cannot paint over those holes.
  const controls = samples.filter((item) => item.risk === 0 || !item.polygons.length)
    .sort((a, b) => b.risk - a.risk)
  for (const sample of controls) {
    const px = (sample.x - west) / (east - west) * width - 0.5
    const py = (north - sample.y) / (north - south) * height - 0.5
    for (const row of [Math.floor(py), Math.ceil(py)]) {
      for (const col of [Math.floor(px), Math.ceil(px)]) {
        if (row < 0 || col < 0 || row >= height || col >= width) continue
        const index = row * width + col
        surface.values[index] = sample.risk
        surface.data.set(sample.risk > 0 ? [...rgb(riskColor(sample.risk)), 255] : [0, 0, 0, 0], index * 4)
      }
    }
  }
  return surface
}

export function sampleRiskSurface(surface, coordinate) {
  if (!surface || !validCoordinate(coordinate)) return { risk: 0, confidence: 0, anchor: false }
  return surfaceSample(surface, ...surface.project.toLocal(coordinate))
}

export function riskSurfaceCanvas(surface, canvas = null) {
  if (!surface) return null
  canvas ??= document.createElement('canvas')
  if (canvas.width !== surface.width) canvas.width = surface.width
  if (canvas.height !== surface.height) canvas.height = surface.height
  const context = canvas.getContext('2d')
  if (!context) throw new Error('Risk heatmap canvas is unavailable.')
  const image = context.createImageData(surface.width, surface.height)
  image.data.set(surface.data)
  context.putImageData(image, 0, 0)
  return canvas
}

export function riskSurfaceImage(surface, createCanvas = () => document.createElement('canvas')) {
  return surface ? riskSurfaceCanvas(surface, createCanvas()).toDataURL('image/png') : null
}

export function applyRiskSurfaceCanvas(map, surface, createCanvas = () => document.createElement('canvas')) {
  let source = map.getSource(RISK_SURFACE_LAYER.source)
  if (source && typeof source.getCanvas !== 'function') {
    if (map.getLayer(RISK_SURFACE_LAYER.id)) map.removeLayer(RISK_SURFACE_LAYER.id)
    map.removeSource(RISK_SURFACE_LAYER.source)
    source = null
  }
  if (!surface) {
    if (!source) return
    const canvas = source.getCanvas()
    canvas.getContext('2d').clearRect(0, 0, canvas.width, canvas.height)
    map.setLayoutProperty(RISK_SURFACE_LAYER.id, 'visibility', 'none')
  } else if (source) {
    riskSurfaceCanvas(surface, source.getCanvas())
    if (JSON.stringify(source.coordinates) !== JSON.stringify(surface.coordinates)) {
      source.setCoordinates(surface.coordinates)
    }
    map.setLayoutProperty(RISK_SURFACE_LAYER.id, 'visibility', 'visible')
  } else {
    const canvas = riskSurfaceCanvas(surface, createCanvas())
    const zoneLayers = ['stage-zones-fill', 'status-zones-fill', 'management-zones-fill', 'cecid-zones-fill', 'orchard-grid']
    const before = map.getStyle().layers.find((layer) => zoneLayers.includes(layer.id))?.id
    map.addSource(RISK_SURFACE_LAYER.source, { type: 'canvas', canvas, animate: false, coordinates: surface.coordinates })
    map.addLayer(RISK_SURFACE_LAYER, before)
    source = map.getSource(RISK_SURFACE_LAYER.source)
  }
  // MapLibre 4.7 requires an explicit upload for same-sized static canvases.
  // pause() prepares the current pixels while playing, then stops animation.
  // This keeps one geographic texture and avoids PNG fetching between hours.
  source.play()
  source.pause()
  map.triggerRepaint()
}
