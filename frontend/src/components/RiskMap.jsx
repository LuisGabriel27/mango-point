import { useEffect, useMemo, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'

const EMPTY_FC = { type: 'FeatureCollection', features: [] }

const HEATMAP_LAYER = {
  id: 'risk-heatmap',
  type: 'heatmap',
  source: 'risk-heatmap-src',
  paint: {
    'heatmap-weight': ['interpolate', ['linear'], ['coalesce', ['get', 'risk'], 0], 0, 0, 1, 1],
    'heatmap-intensity': 2.5,
    'heatmap-color': [
      'interpolate', ['linear'], ['heatmap-density'],
      0, 'rgba(0,0,0,0)',
      0.2, '#22c55e',
      0.4, '#facc15',
      0.65, '#f97316',
      0.85, '#ef4444',
      1.0, '#7f1d1d',
    ],
    'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 15, 25, 18, 65, 20, 120],
    'heatmap-opacity': 0.78,
  },
}

const SATELLITE_URL =
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'

// Drone orthophoto bounds (EPSG:4326) extracted from bpi_map.tif
const ORTHO_COORDINATES = [
  [122.57931578644222, 10.586098142261575], // top-left  [W, N]
  [122.58265914455501, 10.586098142261575], // top-right [E, N]
  [122.58265914455501, 10.582684811249528], // bot-right [E, S]
  [122.57931578644222, 10.582684811249528], // bot-left  [W, S]
]

const DEFAULT_LAT = 10.585
const DEFAULT_LON = 122.580
const DEFAULT_ZOOM = 17.5

const GIS_STATUS_COLORS = {
  healthy: '#22c55e',
  unbagged: '#22c55e',
  infected: '#ef4444',
  infested: '#ef4444',
  bagged: '#3b82f6',
  dead: '#424242',
  history_infected: '#ff9800',
  suspect: '#9c27b0',
}

const MAP_STYLE = {
  version: 8,
  sources: {
    satellite: {
      type: 'raster',
      tiles: [SATELLITE_URL],
      tileSize: 256,
      attribution: 'Tiles &copy; Esri',
    },
  },
  layers: [
    {
      id: 'satellite',
      type: 'raster',
      source: 'satellite',
      minzoom: 0,
      maxzoom: 22,
    },
  ],
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[char]))
}

function riskColor(risk) {
  if (risk == null || !Number.isFinite(risk)) return null
  if (risk >= 0.75) return '#b91c1c'
  if (risk >= 0.5) return '#ef4444'
  if (risk >= 0.25) return '#f59e0b'
  if (risk >= 0.1) return '#facc15'
  return '#22c55e'
}

function normalizeStatus(value) {
  return String(value ?? 'healthy').trim().toLowerCase().replace(/\s+/g, '_')
}

function averageCoordinates(coordinates) {
  const points = coordinates
    .filter((coord) => Array.isArray(coord) && coord.length >= 2)
    .map((coord) => [Number(coord[0]), Number(coord[1])])
    .filter(([lon, lat]) => Number.isFinite(lon) && Number.isFinite(lat))

  if (!points.length) return null

  const lon = points.reduce((sum, point) => sum + point[0], 0) / points.length
  const lat = points.reduce((sum, point) => sum + point[1], 0) / points.length
  return [lon, lat]
}

function geometryCenter(geometry) {
  if (!geometry) return null

  if (geometry.type === 'Point') {
    const lon = Number(geometry.coordinates?.[0])
    const lat = Number(geometry.coordinates?.[1])
    return Number.isFinite(lon) && Number.isFinite(lat) ? [lon, lat] : null
  }

  if (geometry.type === 'MultiPoint' || geometry.type === 'LineString') {
    return averageCoordinates(geometry.coordinates || [])
  }

  if (geometry.type === 'Polygon') {
    const ring = geometry.coordinates?.[0] || []
    const openRing = ring.length > 1 && ring[0]?.[0] === ring.at(-1)?.[0] && ring[0]?.[1] === ring.at(-1)?.[1]
      ? ring.slice(0, -1)
      : ring
    return averageCoordinates(openRing)
  }

  if (geometry.type === 'MultiPolygon') {
    const outerRings = (geometry.coordinates || []).flatMap((polygon) => polygon?.[0] || [])
    return averageCoordinates(outerRings)
  }

  return null
}

function normalizePoints(geojson, treeOverrides = {}) {
  const features = Array.isArray(geojson?.features) ? geojson.features : []

  return features
    .map((feature) => {
      const props = feature.properties || {}
      const geom = feature.geometry || {}
      const center = geometryCenter(geom)
      if (!center) return null

      const [lon, lat] = center

      const treeId = props.tree_id ?? props.Tree_ID ?? props.fid ?? feature.id ?? 'unknown'
      // props.state comes from simulation output; props.status from base GeoJSON
      const rawStatus = props.status ?? props.Status ?? props.state ?? 'healthy'
      const treeIdStr = String(treeId)
      const overrideStatus = treeOverrides[treeIdStr]
      const status = normalizeStatus(overrideStatus ?? rawStatus)
      const crown = Number.parseFloat(props.crown_size ?? props.Crown_Width ?? 5)
      const riskValue = Number(props.risk)
      const risk = Number.isFinite(riskValue) ? riskValue : null
      // Dead/bagged trees always show their status color — never a risk heat color
      const isStatusColored = overrideStatus != null || status === 'dead' || status === 'bagged'
      const color = isStatusColored
        ? (GIS_STATUS_COLORS[status] ?? GIS_STATUS_COLORS.healthy)
        : (riskColor(risk) ?? GIS_STATUS_COLORS[status] ?? GIS_STATUS_COLORS.healthy)

      return {
        tree_id: treeId,
        status,
        lon,
        lat,
        risk,
        crown: Number.isFinite(crown) ? crown : 5,
        color,
      }
    })
    .filter(Boolean)
}

function pointBounds(points) {
  if (!points.length) return null
  const bounds = new maplibregl.LngLatBounds()
  for (const point of points) bounds.extend([point.lon, point.lat])
  return bounds
}

function markerPopupHtml(point) {
  const label = String(point.status).replace(/_/g, ' ')
  const riskLine = point.risk == null ? '' : `<br />Risk: ${(point.risk * 100).toFixed(0)}%`

  return `
    <strong>Tree ${escapeHtml(point.tree_id)}</strong><br />
    Status: ${escapeHtml(label)}<br />
    Crown: ${escapeHtml(point.crown.toFixed(1))} m
    ${riskLine}
  `
}

function makeTreeMarker(point) {
  const el = document.createElement('button')
  el.type = 'button'
  el.className = 'map-tree-marker'
  el.style.setProperty('--marker-color', point.color)
  el.setAttribute('aria-label', `Tree ${point.tree_id}`)
  el.title = `Tree ${point.tree_id}`

  if (point.risk != null && point.risk >= 0.5) {
    el.classList.add('map-tree-marker-risk')
  }

  return el
}

function makeAlertMarker(alert) {
  const el = document.createElement('div')
  el.className = 'map-alert-marker'
  el.title = alert.message || 'Alert'
  return el
}

function removeGrid(map) {
  if (map.getLayer('orchard-grid')) map.removeLayer('orchard-grid')
  if (map.getSource('orchard-grid')) map.removeSource('orchard-grid')
}

// Primary: extract exact grid lines from simulation cell polygon boundaries
function gridGeojsonFromPolygons(geojson) {
  if (!geojson?.features?.length) return null

  const lonEdges = new Set()
  const latEdges = new Set()

  for (const feat of geojson.features) {
    if (feat.geometry?.type !== 'Polygon') continue
    const ring = feat.geometry.coordinates?.[0]
    if (!ring || ring.length < 4) continue
    const lons = ring.slice(0, 4).map((p) => p[0])
    const lats = ring.slice(0, 4).map((p) => p[1])
    lonEdges.add(Math.round(Math.min(...lons) * 1e10) / 1e10)
    lonEdges.add(Math.round(Math.max(...lons) * 1e10) / 1e10)
    latEdges.add(Math.round(Math.min(...lats) * 1e10) / 1e10)
    latEdges.add(Math.round(Math.max(...lats) * 1e10) / 1e10)
  }

  if (lonEdges.size < 2 || latEdges.size < 2) return null

  const lonValues = [...lonEdges].sort((a, b) => a - b)
  const latValues = [...latEdges].sort((a, b) => a - b)
  const lonMin = lonValues[0]
  const lonMax = lonValues[lonValues.length - 1]
  const latMin = latValues[0]
  const latMax = latValues[latValues.length - 1]

  const features = []
  for (const lon of lonValues) {
    features.push({ type: 'Feature', geometry: { type: 'LineString', coordinates: [[lon, latMin], [lon, latMax]] }, properties: {} })
  }
  for (const lat of latValues) {
    features.push({ type: 'Feature', geometry: { type: 'LineString', coordinates: [[lonMin, lat], [lonMax, lat]] }, properties: {} })
  }

  return { type: 'FeatureCollection', features }
}

// Fallback: derive 5m-cell grid lines from tree point positions (no simulation)
function gridGeojsonFromPoints(points) {
  if (points.length < 2) return null

  const lons = points.map((p) => p.lon)
  const lats = points.map((p) => p.lat)
  const minLon = Math.min(...lons), maxLon = Math.max(...lons)
  const minLat = Math.min(...lats), maxLat = Math.max(...lats)

  const cellSizeM = 5.0
  const bufferCells = 2
  const mLat = 111132.0
  const mLon = 111132.0 * Math.cos(((minLat + maxLat) / 2) * (Math.PI / 180))
  if (Math.abs(mLon) < 1e-9) return null

  const cols = Math.max(Math.ceil((maxLon - minLon) * mLon / cellSizeM) + 2 * bufferCells, 10)
  const rows = Math.max(Math.ceil((maxLat - minLat) * mLat / cellSizeM) + 2 * bufferCells, 10)

  const originLon = minLon - bufferCells * cellSizeM / mLon
  const originLat = minLat - bufferCells * cellSizeM / mLat

  const occupiedRows = [], occupiedCols = []
  for (const { lon, lat } of points) {
    const col = Math.floor((lon - originLon) * mLon / cellSizeM)
    const row = Math.floor((lat - originLat) * mLat / cellSizeM)
    if (row >= 0 && row < rows && col >= 0 && col < cols) {
      occupiedRows.push(row)
      occupiedCols.push(col)
    }
  }

  if (!occupiedRows.length) return null

  const rowMin = Math.min(...occupiedRows), rowMax = Math.max(...occupiedRows)
  const colMin = Math.min(...occupiedCols), colMax = Math.max(...occupiedCols)

  const features = []
  for (let c = colMin; c <= colMax + 1; c++) {
    const lonEdge = originLon + c * cellSizeM / mLon
    const latStart = originLat + rowMin * cellSizeM / mLat
    const latEnd = originLat + (rowMax + 1) * cellSizeM / mLat
    features.push({ type: 'Feature', geometry: { type: 'LineString', coordinates: [[lonEdge, latStart], [lonEdge, latEnd]] }, properties: {} })
  }
  for (let r = rowMin; r <= rowMax + 1; r++) {
    const latEdge = originLat + r * cellSizeM / mLat
    const lonStart = originLon + colMin * cellSizeM / mLon
    const lonEnd = originLon + (colMax + 1) * cellSizeM / mLon
    features.push({ type: 'Feature', geometry: { type: 'LineString', coordinates: [[lonStart, latEdge], [lonEnd, latEdge]] }, properties: {} })
  }

  return { type: 'FeatureCollection', features }
}

export default function RiskMap({
  geojson,
  baseGeojson,
  alerts = [],
  treeOverrides = {},
  showGridOverlay = false,
  onTreeClick,
}) {
  const containerRef = useRef(null)
  const mapRef = useRef(null)
  const markersRef = useRef([])
  const mapLoadedRef = useRef(false)

  const activeGeojson = geojson?.features?.length ? geojson : baseGeojson
  const points = useMemo(
    () => normalizePoints(activeGeojson, treeOverrides),
    [activeGeojson, treeOverrides],
  )

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return undefined

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: MAP_STYLE,
      center: [DEFAULT_LON, DEFAULT_LAT],
      zoom: DEFAULT_ZOOM,
      attributionControl: false,
    })

    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-left')
    map.on('error', (event) => {
      if (event?.error) console.warn('Map render warning:', event.error.message)
    })

    map.once('load', () => {
      mapLoadedRef.current = true

      // Drone orthophoto overlay (above satellite, below heatmap/markers)
      map.addSource('ortho-src', {
        type: 'image',
        url: '/ortho.png',
        coordinates: ORTHO_COORDINATES,
      })
      map.addLayer({
        id: 'ortho-layer',
        type: 'raster',
        source: 'ortho-src',
        paint: { 'raster-opacity': 0.92, 'raster-fade-duration': 0 },
      })

      map.addSource('risk-heatmap-src', { type: 'geojson', data: EMPTY_FC })
      map.addLayer(HEATMAP_LAYER)
    })

    const resizeObserver = new ResizeObserver(() => map.resize())
    resizeObserver.observe(containerRef.current)
    mapRef.current = map

    return () => {
      mapLoadedRef.current = false
      resizeObserver.disconnect()
      markersRef.current.forEach((marker) => marker.remove())
      markersRef.current = []
      map.remove()
      mapRef.current = null
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    markersRef.current.forEach((marker) => marker.remove())
    markersRef.current = []

    for (const point of points) {
      const element = makeTreeMarker(point)
      element.addEventListener('click', (event) => {
        event.stopPropagation()
        onTreeClick?.(point)
      })

      const marker = new maplibregl.Marker({ element, anchor: 'center' })
        .setLngLat([point.lon, point.lat])
        .setPopup(
          new maplibregl.Popup({ offset: 14, closeButton: false })
            .setHTML(markerPopupHtml(point)),
        )
        .addTo(map)

      markersRef.current.push(marker)
    }

    for (const alert of alerts) {
      const lon = Number(alert.centroid_lon)
      const lat = Number(alert.centroid_lat)
      if (!Number.isFinite(lon) || !Number.isFinite(lat)) continue

      const marker = new maplibregl.Marker({ element: makeAlertMarker(alert), anchor: 'center' })
        .setLngLat([lon, lat])
        .setPopup(
          new maplibregl.Popup({ offset: 18 })
            .setHTML(`<strong>Alert</strong><br />${escapeHtml(alert.message || '')}`),
        )
        .addTo(map)

      markersRef.current.push(marker)
    }

    const fitMap = () => {
      map.resize()
      if (points.length === 1) {
        map.easeTo({ center: [points[0].lon, points[0].lat], zoom: DEFAULT_ZOOM, duration: 250 })
        return
      }

      const bounds = pointBounds(points)
      if (bounds) {
        map.fitBounds(bounds, {
          padding: { top: 72, right: 96, bottom: 72, left: 72 },
          maxZoom: 19,
          duration: 350,
        })
      }
    }

    if (map.loaded()) fitMap()
    else map.once('load', fitMap)
  }, [points, alerts, onTreeClick])

  // ── Heatmap data update ────────────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current
    if (!map) return undefined

    const data = geojson ?? EMPTY_FC

    const setHeatmapData = () => {
      const src = map.getSource('risk-heatmap-src')
      if (src) src.setData(data)
    }

    if (mapLoadedRef.current) {
      setHeatmapData()
    } else {
      map.once('load', setHeatmapData)
      return () => map.off('load', setHeatmapData)
    }

    return undefined
  }, [geojson])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return undefined

    const updateGrid = () => {
      removeGrid(map)
      if (!showGridOverlay) return

      const source = gridGeojsonFromPolygons(activeGeojson) ?? gridGeojsonFromPoints(points)
      if (!source) return

      map.addSource('orchard-grid', { type: 'geojson', data: source })
      map.addLayer({
        id: 'orchard-grid',
        type: 'line',
        source: 'orchard-grid',
        paint: {
          'line-color': 'rgba(20, 34, 30, 0.46)',
          'line-opacity': 1,
          'line-width': 1,
        },
      })
    }

    if (map.loaded()) updateGrid()
    else map.once('load', updateGrid)

    return () => {
      if (mapRef.current) removeGrid(mapRef.current)
    }
  }, [points, activeGeojson, showGridOverlay])

  return (
    <div className="risk-map-root">
      <div ref={containerRef} className="risk-map-canvas" />
      {!points.length && (
        <div className="risk-map-empty">
          Loading orchard map...
        </div>
      )}
    </div>
  )
}
