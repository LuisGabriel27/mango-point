import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import guimarasWondersFarmOrthophotoUrl from '../assets/guimaras-wonders-farm-orthophoto.png'
import {
  GUIMARAS_WONDERS_FARM_ID,
  GUIMARAS_WONDERS_FARM_OVERLAY_COORDINATES,
} from '../utils/bundledOrchards'
import { simplifyLassoCoordinates } from '../utils/zoneSelection'
import { interpretCecidTree } from '../utils/cecidMapInterpretation'
import { initialSourceDetails, interpretSimulationTree, resolveTreeStatuses } from '../utils/simulationMapInterpretation'
import { runWhenMapReady } from '../utils/mapReady'
import { geometryCenter } from '../utils/mapGeometry'
import { captureMapSnapshot, waitForMapSnapshot } from '../utils/mapSnapshot'
import { buildRiskSurface, riskColor, applyRiskSurfaceCanvas } from '../utils/riskSurface'

const EMPTY_FC = { type: 'FeatureCollection', features: [] }

const SATELLITE_URL =
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
// OpenStreetMap raster tiles. Used as a fallback underlayer so the basemap
// keeps something visible past Esri's max imagery zoom (~19 in rural areas).
const OSM_URLS = [
  'https://a.tile.openstreetmap.org/{z}/{x}/{y}.png',
  'https://b.tile.openstreetmap.org/{z}/{x}/{y}.png',
  'https://c.tile.openstreetmap.org/{z}/{x}/{y}.png',
]
const API_BASE = import.meta.env.VITE_API_BASE || ''

// Drone orthophoto bounds (EPSG:4326) extracted from bpi_map.tif
const ORTHO_COORDINATES = [
  [122.57931578644222, 10.586098142261575], // top-left  [W, N]
  [122.58265914455501, 10.586098142261575], // top-right [E, N]
  [122.58265914455501, 10.582684811249528], // bot-right [E, S]
  [122.57931578644222, 10.582684811249528], // bot-left  [W, S]
]

const DEFAULT_ORTHOPHOTO_OVERLAY = {
  url: '/ortho.png',
  coordinates: ORTHO_COORDINATES,
}

const GUIMARAS_WONDERS_FARM_OVERLAY = {
  url: guimarasWondersFarmOrthophotoUrl,
  coordinates: GUIMARAS_WONDERS_FARM_OVERLAY_COORDINATES,
}

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

const STAGE_ZONE_FILL_LAYER = {
  id: 'stage-zones-fill',
  type: 'fill',
  source: 'stage-zones-src',
  paint: {
    'fill-color': [
      'match', ['get', 'stage'],
      'dormant', '#64748b',
      'flowering', '#ec4899',
      'fruitlet', '#f59e0b',
      'mature', '#16a34a',
      '#0f5132',
    ],
    'fill-opacity': 0.28,
  },
}

const STAGE_ZONE_LINE_LAYER = {
  id: 'stage-zones-line',
  type: 'line',
  source: 'stage-zones-src',
  paint: {
    'line-color': [
      'match', ['get', 'stage'],
      'dormant', '#64748b',
      'flowering', '#ec4899',
      'fruitlet', '#f59e0b',
      'mature', '#16a34a',
      '#0f5132',
    ],
    'line-width': 3,
    'line-opacity': 0.9,
  },
}

const STAGE_DRAFT_LINE_LAYER = {
  id: 'stage-zone-draft-line',
  type: 'line',
  source: 'stage-zone-draft-src',
  filter: ['==', ['geometry-type'], 'LineString'],
  paint: {
    'line-color': '#0f5132',
    'line-width': 2,
    'line-dasharray': [2, 1],
  },
}

const STAGE_DRAFT_VERTEX_LAYER = {
  id: 'stage-zone-draft-vertices',
  type: 'circle',
  source: 'stage-zone-draft-src',
  filter: ['==', ['geometry-type'], 'Point'],
  paint: {
    'circle-radius': 5,
    'circle-color': '#ffffff',
    'circle-stroke-color': '#0f5132',
    'circle-stroke-width': 2,
  },
}

const STAGE_COLORS = {
  dormant: '#64748b',
  flowering: '#ec4899',
  fruitlet: '#f59e0b',
  mature: '#16a34a',
}

const STATUS_ZONE_COLORS = {
  healthy: '#22c55e',
  infected: '#ef4444',
  bagged: '#3b82f6',
  dead: '#424242',
  history_infected: '#ff9800',
  suspect: '#9c27b0',
}

const STATUS_ZONE_FILL_LAYER = {
  id: 'status-zones-fill',
  type: 'fill',
  source: 'status-zones-src',
  paint: {
    'fill-color': [
      'match', ['get', 'status'],
      'healthy', '#22c55e',
      'infected', '#ef4444',
      'bagged', '#3b82f6',
      'dead', '#424242',
      'history_infected', '#ff9800',
      'suspect', '#9c27b0',
      '#f59e0b',
    ],
    'fill-opacity': 0.22,
  },
}

const STATUS_ZONE_LINE_LAYER = {
  id: 'status-zones-line',
  type: 'line',
  source: 'status-zones-src',
  paint: {
    'line-color': [
      'match', ['get', 'status'],
      'healthy', '#22c55e',
      'infected', '#ef4444',
      'bagged', '#3b82f6',
      'dead', '#424242',
      'history_infected', '#ff9800',
      'suspect', '#9c27b0',
      '#f59e0b',
    ],
    'line-width': 3,
    'line-opacity': 0.9,
  },
}

const STATUS_DRAFT_LINE_LAYER = {
  id: 'status-zone-draft-line',
  type: 'line',
  source: 'status-zone-draft-src',
  filter: ['==', ['geometry-type'], 'LineString'],
  paint: {
    'line-color': '#e65100',
    'line-width': 2,
    'line-dasharray': [2, 1],
  },
}

const STATUS_DRAFT_VERTEX_LAYER = {
  id: 'status-zone-draft-vertices',
  type: 'circle',
  source: 'status-zone-draft-src',
  filter: ['==', ['geometry-type'], 'Point'],
  paint: {
    'circle-radius': 5,
    'circle-color': '#ffffff',
    'circle-stroke-color': '#e65100',
    'circle-stroke-width': 2,
  },
}

const MANAGEMENT_ZONE_FILL_LAYER = {
  id: 'management-zones-fill',
  type: 'fill',
  source: 'management-zones-src',
  paint: {
    'fill-color': ['coalesce', ['get', 'color'], '#2563eb'],
    'fill-opacity': 0.13,
  },
}

const MANAGEMENT_ZONE_LINE_LAYER = {
  id: 'management-zones-line',
  type: 'line',
  source: 'management-zones-src',
  paint: {
    'line-color': ['coalesce', ['get', 'color'], '#2563eb'],
    'line-width': 3,
    'line-opacity': 0.95,
  },
}

const MANAGEMENT_DRAFT_LINE_LAYER = {
  id: 'management-zone-draft-line',
  type: 'line',
  source: 'management-zone-draft-src',
  filter: ['==', ['geometry-type'], 'LineString'],
  paint: { 'line-color': '#2563eb', 'line-width': 2, 'line-dasharray': [2, 1] },
}

const MANAGEMENT_DRAFT_VERTEX_LAYER = {
  id: 'management-zone-draft-vertices',
  type: 'circle',
  source: 'management-zone-draft-src',
  filter: ['==', ['geometry-type'], 'Point'],
  paint: {
    'circle-radius': 5,
    'circle-color': '#ffffff',
    'circle-stroke-color': '#2563eb',
    'circle-stroke-width': 2,
  },
}

const CECID_ZONE_FILL_LAYER = {
  id: 'cecid-zones-fill',
  type: 'fill',
  source: 'cecid-zones-src',
  paint: {
    'fill-color': [
      'case', ['boolean', ['get', 'legacy'], false], '#64748b',
      ['match', ['get', 'density'],
        'sparse', '#86efac',
        'dense', '#166534',
        '#22c55e'],
    ],
    'fill-opacity': [
      'case', ['boolean', ['get', 'legacy'], false], 0.12,
      ['match', ['get', 'density'],
        'sparse', 0.16,
        'dense', 0.34,
        0.24],
    ],
  },
}

const CECID_ZONE_LINE_LAYER = {
  id: 'cecid-zones-line',
  type: 'line',
  source: 'cecid-zones-src',
  paint: {
    'line-color': [
      'case', ['boolean', ['get', 'legacy'], false], '#64748b',
      ['match', ['get', 'density'],
        'sparse', '#4ade80',
        'dense', '#14532d',
        '#15803d'],
    ],
    'line-width': 3,
    'line-dasharray': [2, 1],
  },
}

const CECID_DRAFT_LINE_LAYER = {
  id: 'cecid-zone-draft-line',
  type: 'line',
  source: 'cecid-zone-draft-src',
  filter: ['==', ['geometry-type'], 'LineString'],
  paint: { 'line-color': '#15803d', 'line-width': 2, 'line-dasharray': [2, 1] },
}

const CECID_DRAFT_VERTEX_LAYER = {
  id: 'cecid-zone-draft-vertices',
  type: 'circle',
  source: 'cecid-zone-draft-src',
  filter: ['==', ['geometry-type'], 'Point'],
  paint: {
    'circle-radius': 5,
    'circle-color': '#ffffff',
    'circle-stroke-color': '#15803d',
    'circle-stroke-width': 2,
  },
}

const MAP_STYLE = {
  version: 8,
  sources: {
    osm: {
      type: 'raster',
      tiles: OSM_URLS,
      tileSize: 256,
      // OSM serves tiles up to z19; MapLibre overzooms above that instead of
      // requesting unavailable tiles, so the basemap never goes blank.
      maxzoom: 19,
      attribution: '&copy; OpenStreetMap contributors',
    },
    satellite: {
      type: 'raster',
      tiles: [SATELLITE_URL],
      tileSize: 256,
      // Esri World Imagery caps at ~z19 in rural Guimaras; tell MapLibre so
      // it overzooms the z19 tile instead of showing "Map data not yet
      // available" placeholders for z20+ requests.
      maxzoom: 19,
      attribution: 'Tiles &copy; Esri',
    },
  },
  layers: [
    {
      id: 'osm',
      type: 'raster',
      source: 'osm',
      minzoom: 0,
      maxzoom: 22,
    },
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

function normalizePoints(
  geojson,
  treeOverrides = {},
  stageOverrides = {},
  stageZones = [],
  pestType = 'fruitfly',
  cecidMapMode = 'representative',
) {
  const features = Array.isArray(geojson?.features) ? geojson.features : []
  // Stage properties can remain in an older orchard GeoJSON after its zones
  // are deleted. Only treat them as active map inputs while stage context
  // exists; otherwise Cecid eligibility would incorrectly gray those trees.
  const hasStageContext = Array.isArray(stageZones) && stageZones.length > 0

  return features
    .map((feature) => {
      const props = feature.properties || {}
      const geom = feature.geometry || {}
      const center = geometryCenter(geom)
      if (!center) return null

      const [lon, lat] = center

      const treeId = props.tree_id ?? props.Tree_ID ?? props.fid ?? feature.id ?? 'unknown'
      // props.state comes from simulation output; props.status from base GeoJSON
      const treeIdStr = String(treeId)
      const overrideStatus = treeOverrides[treeIdStr]
      const overrideStage = stageOverrides[treeIdStr] ?? null
      const stage = hasStageContext
        ? (overrideStage ?? props.stage ?? props.Stage ?? null)
        : null
      // A saved/manual status is an input for the next run. The result's
      // state describes what actually happened in the displayed realization.
      const { inputStatus, status } = resolveTreeStatuses(props, overrideStatus)
      const crown = Number.parseFloat(props.crown_size ?? props.Crown_Width ?? 5)
      const riskValue = props.risk == null || props.risk === '' ? NaN : Number(props.risk)
      const risk = Number.isFinite(riskValue) ? riskValue : null
      const isCecid = pestType === 'cecid'
      const cecid = isCecid
        ? interpretCecidTree({ ...props, stage, state: status }, cecidMapMode)
        : null
      const interpretation = cecid ?? interpretSimulationTree({ ...props, state: status }, cecidMapMode)
      const displayRisk = interpretation.displayRisk
      // Dead/bagged trees always show their status color — never a risk heat color
      const isStatusColored = status === 'dead' || status === 'bagged' || displayRisk == null
      const color = isCecid && cecid?.eligible === false && !isStatusColored
        ? '#6b7280'
        : isStatusColored
          ? (GIS_STATUS_COLORS[status] ?? GIS_STATUS_COLORS.healthy)
          : (riskColor(displayRisk) ?? GIS_STATUS_COLORS[status] ?? GIS_STATUS_COLORS.healthy)

      return {
        tree_id: treeId,
        status,
        input_status: inputStatus,
        lon,
        lat,
        geometry: geom,
        risk,
        display_risk: displayRisk,
        crown: Number.isFinite(crown) ? crown : 5,
        color,
        stage,
        stage_color: STAGE_COLORS[String(overrideStage ?? '').toLowerCase()] ?? null,
        cecid_source: Boolean(props.cecid_source),
        cecid_source_pressure: Number(props.cecid_source_pressure || 0),
        cecid_source_assumed: Boolean(props.cecid_source_assumed),
        cecid_source_label: props.cecid_source_label || null,
        is_cecid: isCecid,
        cecid,
        interpretation,
        initialSource: initialSourceDetails(props, pestType),
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

function imageCoordinateBounds(coordinates) {
  if (!validImageCoordinates(coordinates)) return null
  const bounds = new maplibregl.LngLatBounds()
  for (const point of coordinates) bounds.extend([Number(point[0]), Number(point[1])])
  return bounds
}

const DEFAULT_FIT_PADDING = { top: 72, right: 96, bottom: 72, left: 72 }
const REPORT_FIT_PADDING = { top: 24, right: 24, bottom: 24, left: 24 }

function reportContentBounds(points, zoneCollections) {
  const bounds = new maplibregl.LngLatBounds()
  let hasCoordinates = false
  for (const point of points) {
    if (!Number.isFinite(point.lon) || !Number.isFinite(point.lat)) continue
    bounds.extend([point.lon, point.lat])
    hasCoordinates = true
  }
  for (const zones of zoneCollections) {
    for (const zone of zones || []) {
      for (const coordinate of zone?.coordinates || []) {
        const lon = Number(coordinate?.[0])
        const lat = Number(coordinate?.[1])
        if (!Number.isFinite(lon) || !Number.isFinite(lat)) continue
        bounds.extend([lon, lat])
        hasCoordinates = true
      }
    }
  }
  return hasCoordinates ? bounds : null
}

function fitMapToBounds(map, bounds, duration = 450, padding = DEFAULT_FIT_PADDING) {
  if (!bounds) return false
  map.fitBounds(bounds, {
    padding,
    maxZoom: 19,
    duration,
  })
  return true
}

function markerPopupHtml(point) {
  const label = String(point.status).replace(/_/g, ' ')
  const riskLine = point.display_risk == null ? ''
    : `<br /><strong>${escapeHtml(point.interpretation.displayRiskLabel)}:</strong> ${(point.display_risk * 100).toFixed(0)}%`
  const stageLine = point.stage == null ? '' : `<br />Stage: ${escapeHtml(String(point.stage))}`
  const sourceLine = point.cecid_source
    ? `<br /><strong>Cecid soil source:</strong> ${escapeHtml(point.cecid_source_label || 'Source anchor')}`
      + `<br />Pressure: ${escapeHtml(point.cecid_source_pressure.toFixed(1))}×`
      + (point.cecid_source_assumed ? '<br /><em>Assumed source in one run</em>' : '')
    : ''
  const initialSourceLine = point.initialSource
    ? `<br /><strong>${point.initialSource.assumed ? 'Assumed source in one run' : 'Known current source'}:</strong> ${escapeHtml(point.initialSource.label)}`
      + `<br /><em>${escapeHtml(point.initialSource.explanation)}</em>`
    : ''

  if (point.is_cecid && point.cecid) {
    const cecid = point.cecid
    const eligibility = cecid.eligible === true
      ? 'Eligible fruitlet'
      : cecid.eligible === false ? 'Not eligible' : 'Eligibility unknown'
    const mapValueLine = cecid.displayRisk == null || cecid.eligible === false
      ? ''
      : `<br /><strong>${escapeHtml(cecid.displayRiskLabel)}:</strong> ${(cecid.displayRisk * 100).toFixed(0)}%`
    const frequencyLine = cecid.hasEnsemble && cecid.displayMode !== 'likelihood'
      ? `<br /><strong>Repeated-run frequency:</strong> ${(cecid.ensembleFrequency * 100).toFixed(0)}% (${cecid.ensembleCount}/${cecid.ensembleRuns})`
      : ''
    const cumulativeLine = cecid.cumulativeProbability == null
      ? ''
      : `<br /><strong>Representative cumulative chance:</strong> ${(cecid.cumulativeProbability * 100).toFixed(1)}%`
    const peakLine = cecid.peakHourlyRisk == null
      ? ''
      : `<br />Highest eligible-hour chance: ${(cecid.peakHourlyRisk * 100).toFixed(1)}%`

    return `
      <strong>Tree ${escapeHtml(point.tree_id)}</strong><br />
      <strong>${escapeHtml(cecid.outcomeLabel)}</strong><br />
      Stage: ${escapeHtml(String(point.stage ?? 'unknown'))} · ${escapeHtml(eligibility)}
      ${mapValueLine}
      ${frequencyLine}
      ${cumulativeLine}
      ${peakLine}<br />
      Exposure hours: ${cecid.exposureHours} (${cecid.localExposureHours} local, ${cecid.externalExposureHours} outside)<br />
      Route: ${escapeHtml(cecid.exposureRouteLabel)}<br />
      <strong>Why this tree?</strong> ${escapeHtml(cecid.explanation)}
      <br /><em>${escapeHtml(cecid.displayExplanation)}</em>
      ${sourceLine}
      ${initialSourceLine}
    `
  }

  return `
    <strong>Tree ${escapeHtml(point.tree_id)}</strong><br />
    Status: ${escapeHtml(label)}<br />
    Crown: ${escapeHtml(point.crown.toFixed(1))} m
    ${riskLine}
    ${stageLine}
    ${sourceLine}
    ${initialSourceLine}
    ${point.risk == null ? '' : `<br /><strong>${escapeHtml(point.interpretation.outcomeLabel)}</strong><br /><em>${escapeHtml(point.interpretation.displayExplanation)}</em>`}
  `
}

function makeTreeMarker(point) {
  const el = document.createElement('button')
  el.type = 'button'
  el.className = 'map-tree-marker'
  el.style.setProperty('--marker-color', point.color)
  el.setAttribute('aria-label', `Tree ${point.tree_id}`)
  el.title = `Tree ${point.tree_id}`

  if (point.stage_color) {
    el.classList.add('map-tree-marker-stage')
    el.style.setProperty('--stage-color', point.stage_color)
  }

  if (point.display_risk != null && point.display_risk >= 0.5) {
    el.classList.add('map-tree-marker-risk')
  }

  if (point.is_cecid && point.cecid?.eligible === false) {
    el.classList.add('map-tree-marker-ineligible')
  }

  if (point.cecid_source || point.initialSource) {
    el.classList.add('map-tree-marker-cecid-source')
    el.dataset.sourceBadge = point.is_cecid ? 'S' : point.initialSource?.badge || 'S'
    el.title = `${point.initialSource?.label || point.cecid_source_label || 'Cecid soil source'}${point.initialSource?.assumed || point.cecid_source_assumed ? ' (assumed in one run)' : ''}`
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

function validImageCoordinates(coordinates) {
  return Array.isArray(coordinates)
    && coordinates.length === 4
    && coordinates.every((point) => (
      Array.isArray(point)
      && point.length >= 2
      && Number.isFinite(Number(point[0]))
      && Number.isFinite(Number(point[1]))
    ))
}

function isGuimarasWondersFarm(viewportKey, overlayUrl) {
  const orchardKey = String(viewportKey ?? '').trim().toLowerCase()
  const imageUrl = String(overlayUrl ?? '').trim().toLowerCase()
  return orchardKey === GUIMARAS_WONDERS_FARM_ID
    || orchardKey.startsWith(`${GUIMARAS_WONDERS_FARM_ID}:`)
    || imageUrl.includes(`/orchards/${GUIMARAS_WONDERS_FARM_ID}/`)
}

function normalizedOverlay(overlay, viewportKey) {
  if (overlay === false) return null
  const isGuimarasWonders = isGuimarasWondersFarm(viewportKey, overlay?.url)
  if (overlay?.url && validImageCoordinates(overlay.coordinates)) {
    return {
      url: overlay.url,
      coordinates: overlay.coordinates.map((point) => [Number(point[0]), Number(point[1])]),
      fallbackUrl: isGuimarasWonders ? GUIMARAS_WONDERS_FARM_OVERLAY.url : null,
    }
  }
  if (isGuimarasWonders) return GUIMARAS_WONDERS_FARM_OVERLAY
  return DEFAULT_ORTHOPHOTO_OVERLAY
}

function closedRing(coordinates) {
  if (!Array.isArray(coordinates) || coordinates.length < 3) return []
  const first = coordinates[0]
  const last = coordinates[coordinates.length - 1]
  const ring = coordinates.map((point) => [Number(point[0]), Number(point[1])])
  if (first?.[0] !== last?.[0] || first?.[1] !== last?.[1]) {
    ring.push([Number(first[0]), Number(first[1])])
  }
  return ring
}

function stageZoneGeojson(zones) {
  return {
    type: 'FeatureCollection',
    features: (zones || [])
      .map((zone) => {
        const ring = closedRing(zone.coordinates)
        if (ring.length < 4) return null
        return {
          type: 'Feature',
          geometry: { type: 'Polygon', coordinates: [ring] },
          properties: {
            id: zone.id,
            stage: zone.stage,
            tree_count: zone.tree_count ?? 0,
          },
        }
      })
      .filter(Boolean),
  }
}

function statusZoneGeojson(zones) {
  return {
    type: 'FeatureCollection',
    features: (zones || [])
      .map((zone) => {
        const ring = closedRing(zone.coordinates)
        if (ring.length < 4) return null
        return {
          type: 'Feature',
          geometry: { type: 'Polygon', coordinates: [ring] },
          properties: {
            id: zone.id,
            status: zone.status,
            tree_count: zone.tree_count ?? 0,
          },
        }
      })
      .filter(Boolean),
  }
}

function managementZoneGeojson(zones) {
  return {
    type: 'FeatureCollection',
    features: (zones || [])
      .map((zone) => {
        const ring = closedRing(zone.coordinates)
        if (ring.length < 4) return null
        return {
          type: 'Feature',
          geometry: { type: 'Polygon', coordinates: [ring] },
          properties: {
            id: zone.id,
            label: zone.label,
            color: zone.color || '#2563eb',
            tree_count: zone.tree_count ?? 0,
          },
        }
      })
      .filter(Boolean),
  }
}

function cecidZoneGeojson(weedZones, legacyZones) {
  const weedFeatures = (weedZones || [])
    .map((zone) => {
      const ring = closedRing(zone.coordinates)
      if (ring.length < 4) return null
      return {
        type: 'Feature',
        geometry: { type: 'Polygon', coordinates: [ring] },
        properties: {
          id: zone.id,
          label: zone.label,
          density: zone.density || 'moderate',
          tree_count: zone.tree_count ?? 0,
          legacy: false,
          assumption: 'Adult shelter and short-hop relay only; weeds are not Cecid sources or hosts',
        },
      }
    })
    .filter(Boolean)
  const legacyFeatures = (legacyZones || [])
    .map((zone) => {
      const ring = closedRing(zone.coordinates)
      if (ring.length < 4) return null
      return {
        type: 'Feature',
        geometry: { type: 'Polygon', coordinates: [ring] },
        properties: {
          id: zone.id,
          label: zone.label || 'Legacy Cecid emergence assumption',
          pressure: zone.pressure || 'medium',
          legacy: true,
          assumption: 'Read-only historical source assumption; not converted to weed habitat',
        },
      }
    })
    .filter(Boolean)
  return {
    type: 'FeatureCollection',
    features: [...weedFeatures, ...legacyFeatures],
  }
}

function stageDraftGeojson(draft) {
  const coords = Array.isArray(draft) ? draft : []
  const features = coords.map((coord, index) => ({
    type: 'Feature',
    geometry: { type: 'Point', coordinates: coord },
    properties: { index },
  }))
  if (coords.length >= 2) {
    const lineCoords = coords.length >= 3 ? [...coords, coords[0]] : coords
    features.unshift({
      type: 'Feature',
      geometry: { type: 'LineString', coordinates: lineCoords },
      properties: {},
    })
  }
  return { type: 'FeatureCollection', features }
}

function ensureStageZoneLayers(map) {
  if (!map.getSource('stage-zones-src')) {
    map.addSource('stage-zones-src', { type: 'geojson', data: EMPTY_FC })
  }
  if (!map.getLayer('stage-zones-fill')) map.addLayer(STAGE_ZONE_FILL_LAYER)
  if (!map.getLayer('stage-zones-line')) map.addLayer(STAGE_ZONE_LINE_LAYER)

  if (!map.getSource('stage-zone-draft-src')) {
    map.addSource('stage-zone-draft-src', { type: 'geojson', data: EMPTY_FC })
  }
  if (!map.getLayer('stage-zone-draft-line')) map.addLayer(STAGE_DRAFT_LINE_LAYER)
  if (!map.getLayer('stage-zone-draft-vertices')) map.addLayer(STAGE_DRAFT_VERTEX_LAYER)
}

function ensureStatusZoneLayers(map) {
  if (!map.getSource('status-zones-src')) {
    map.addSource('status-zones-src', { type: 'geojson', data: EMPTY_FC })
  }
  if (!map.getLayer('status-zones-fill')) map.addLayer(STATUS_ZONE_FILL_LAYER)
  if (!map.getLayer('status-zones-line')) map.addLayer(STATUS_ZONE_LINE_LAYER)

  if (!map.getSource('status-zone-draft-src')) {
    map.addSource('status-zone-draft-src', { type: 'geojson', data: EMPTY_FC })
  }
  if (!map.getLayer('status-zone-draft-line')) map.addLayer(STATUS_DRAFT_LINE_LAYER)
  if (!map.getLayer('status-zone-draft-vertices')) map.addLayer(STATUS_DRAFT_VERTEX_LAYER)
}

function ensureManagementZoneLayers(map) {
  if (!map.getSource('management-zones-src')) {
    map.addSource('management-zones-src', { type: 'geojson', data: EMPTY_FC })
  }
  if (!map.getLayer('management-zones-fill')) map.addLayer(MANAGEMENT_ZONE_FILL_LAYER)
  if (!map.getLayer('management-zones-line')) map.addLayer(MANAGEMENT_ZONE_LINE_LAYER)

  if (!map.getSource('management-zone-draft-src')) {
    map.addSource('management-zone-draft-src', { type: 'geojson', data: EMPTY_FC })
  }
  if (!map.getLayer('management-zone-draft-line')) map.addLayer(MANAGEMENT_DRAFT_LINE_LAYER)
  if (!map.getLayer('management-zone-draft-vertices')) map.addLayer(MANAGEMENT_DRAFT_VERTEX_LAYER)
}

function ensureCecidZoneLayers(map) {
  if (!map.getSource('cecid-zones-src')) {
    map.addSource('cecid-zones-src', { type: 'geojson', data: EMPTY_FC })
  }
  if (!map.getLayer('cecid-zones-fill')) map.addLayer(CECID_ZONE_FILL_LAYER)
  if (!map.getLayer('cecid-zones-line')) map.addLayer(CECID_ZONE_LINE_LAYER)

  if (!map.getSource('cecid-zone-draft-src')) {
    map.addSource('cecid-zone-draft-src', { type: 'geojson', data: EMPTY_FC })
  }
  if (!map.getLayer('cecid-zone-draft-line')) map.addLayer(CECID_DRAFT_LINE_LAYER)
  if (!map.getLayer('cecid-zone-draft-vertices')) map.addLayer(CECID_DRAFT_VERTEX_LAYER)
}

async function resolveOverlayImageUrl(url, fallbackUrl = null) {
  if (!url || !url.startsWith('/orchards/')) return { imageUrl: url, objectUrl: null }

  const token = sessionStorage.getItem('access_token')
  const assetUrl = API_BASE
    ? `${API_BASE.replace(/\/$/, '')}${url}`
    : url
  try {
    const response = await fetch(assetUrl, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      cache: 'no-store',
    })
    const contentType = response.headers.get('content-type') ?? ''
    if (response.ok && contentType.startsWith('image/')) {
      const objectUrl = URL.createObjectURL(await response.blob())
      return { imageUrl: objectUrl, objectUrl }
    }
    if (fallbackUrl) return { imageUrl: fallbackUrl, objectUrl: null }
    throw new Error(`Unable to load orchard orthophoto (${response.status})`)
  } catch (error) {
    if (fallbackUrl) return { imageUrl: fallbackUrl, objectUrl: null }
    throw error
  }
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

export default forwardRef(function RiskMap({
  geojson,
  baseGeojson,
  alerts = [],
  treeOverrides = {},
  stageOverrides = {},
  stageZones = [],
  stageZoneDrawing = false,
  stageZoneDraft = [],
  onStageZoneMapClick,
  onStageZoneDraftChange,
  statusZones = [],
  statusZoneDrawing = false,
  statusZoneDraft = [],
  onStatusZoneMapClick,
  onStatusZoneDraftChange,
  managementZones = [],
  managementZoneDrawing = false,
  managementZoneDraft = [],
  onManagementZoneMapClick,
  onManagementZoneDraftChange,
  cecidWeedZones = [],
  legacyCecidEmergenceZones = [],
  cecidZoneDrawing = false,
  cecidZoneDraft = [],
  onCecidZoneMapClick,
  onCecidZoneDraftChange,
  zoneDrawMode = 'polygon',
  zoneVisibility = { stage: true, status: true, management: true, cecid: true },
  orthophotoOverlay = null,
  viewportKey = 'default',
  fitToOrthophoto = true,
  showGridOverlay = false,
  pestType = 'fruitfly',
  cecidMapMode = 'representative',
  onTreeClick,
  reportMode = false,
}, ref) {
  const containerRef = useRef(null)
  const mapRef = useRef(null)
  const markersRef = useRef([])
  const mapLoadedRef = useRef(false)
  const overlayPendingRef = useRef(true)
  const heatmapPendingRef = useRef(true)
  // Tracks whether the orthophoto image is currently being fetched/applied,
  // so the UI can render a spinner. The GWF overlay is ~6 MB and used to
  // appear "broken" while it silently downloaded.
  const [overlayLoading, setOverlayLoading] = useState(false)

  const activeGeojson = geojson?.features?.length ? geojson : baseGeojson
  const activeOverlay = useMemo(
    () => normalizedOverlay(orthophotoOverlay, viewportKey),
    [orthophotoOverlay, viewportKey],
  )
  const points = useMemo(
    () => normalizePoints(
      activeGeojson,
      treeOverrides,
      stageOverrides,
      stageZones,
      pestType,
      cecidMapMode,
    ),
    [activeGeojson, treeOverrides, stageOverrides, stageZones, pestType, cecidMapMode],
  )
  const heatmapSurface = useMemo(
    () => geojson?.features?.length ? buildRiskSurface(geojson, pestType, cecidMapMode, points) : null,
    [cecidMapMode, geojson, pestType, points],
  )
  // Risk/state changes during playback must not restart camera fitting.
  const pointLocationsKey = JSON.stringify(points.map(({ lon, lat }) => [lon, lat]))
  const fitPoints = useMemo(
    () => JSON.parse(pointLocationsKey).map(([lon, lat]) => ({ lon, lat })),
    [pointLocationsKey],
  )
  const reportZoneCoordinatesKey = JSON.stringify(reportMode
    ? [stageZones, statusZones, managementZones, cecidWeedZones, legacyCecidEmergenceZones]
      .flatMap((zones) => zones.map((zone) => zone.coordinates))
    : [])
  const fitZones = useMemo(
    () => JSON.parse(reportZoneCoordinatesKey).map((coordinates) => ({ coordinates })),
    [reportZoneCoordinatesKey],
  )

  useImperativeHandle(ref, () => ({
    async captureImage() {
      const map = mapRef.current
      if (!map || !reportMode) throw new Error('The report map is not ready.')
      await waitForMapSnapshot(map, () => (
        mapRef.current === map && mapLoadedRef.current && !overlayPendingRef.current && !heatmapPendingRef.current
      ))
      return captureMapSnapshot(map, points)
    },
  }), [points, reportMode])

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return undefined

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: MAP_STYLE,
      center: [DEFAULT_LON, DEFAULT_LAT],
      zoom: DEFAULT_ZOOM,
      attributionControl: false,
      preserveDrawingBuffer: reportMode,
      interactive: !reportMode,
      ...(reportMode ? { pixelRatio: 2 } : {}),
    })

    if (!reportMode) map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-left')
    map.on('error', (event) => {
      if (event?.error) console.warn('Map render warning:', event.error.message)
    })

    map.once('load', () => {
      mapLoadedRef.current = true

      ensureStageZoneLayers(map)
      ensureStatusZoneLayers(map)
      ensureManagementZoneLayers(map)
      ensureCecidZoneLayers(map)
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
    if (!map) return undefined

    let cancelled = false
    let objectUrl = null
    overlayPendingRef.current = true

    const applyOverlay = async () => {
      if (!activeOverlay) {
        if (map.getLayer('ortho-layer')) map.removeLayer('ortho-layer')
        if (map.getSource('ortho-src')) map.removeSource('ortho-src')
        overlayPendingRef.current = false
        return
      }
      // Show the spinner only when we actually need to fetch the image over
      // the network. Static `/ortho.png` (BPI default) resolves instantly,
      // so flashing a spinner would be noise.
      const needsNetworkFetch = typeof activeOverlay.url === 'string'
        && activeOverlay.url.startsWith('/orchards/')
      if (needsNetworkFetch) setOverlayLoading(true)

      try {
        if (map.getLayer('ortho-layer')) map.removeLayer('ortho-layer')
        if (map.getSource('ortho-src')) map.removeSource('ortho-src')

        const resolved = await resolveOverlayImageUrl(
          activeOverlay.url,
          activeOverlay.fallbackUrl,
        )
        if (cancelled) {
          if (resolved.objectUrl) URL.revokeObjectURL(resolved.objectUrl)
          return
        }

        objectUrl = resolved.objectUrl

        map.addSource('ortho-src', {
          type: 'image',
          url: resolved.imageUrl,
          coordinates: activeOverlay.coordinates,
        })
        const overlayLayer = {
          id: 'ortho-layer',
          type: 'raster',
          source: 'ortho-src',
          paint: { 'raster-opacity': 1, 'raster-fade-duration': 0 },
        }
        const beforeLayer = map.getLayer('risk-heatmap') ? 'risk-heatmap'
          : map.getLayer('stage-zones-fill') ? 'stage-zones-fill' : undefined
        if (beforeLayer) map.addLayer(overlayLayer, beforeLayer)
        else map.addLayer(overlayLayer)
      } catch (error) {
        console.warn('Orthophoto overlay unavailable:', error.message)
      } finally {
        if (!cancelled) {
          overlayPendingRef.current = false
          setOverlayLoading(false)
        }
      }
    }

    const cleanup = runWhenMapReady(map, mapLoadedRef.current, applyOverlay)

    return () => {
      cleanup()
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [activeOverlay])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return undefined

    const updateStageZones = () => {
      ensureStageZoneLayers(map)
      map.getSource('stage-zones-src')?.setData(stageZoneGeojson(stageZones))
      map.getSource('stage-zone-draft-src')?.setData(stageDraftGeojson(stageZoneDraft))
      if (map.getLayer('stage-zones-fill')) map.moveLayer('stage-zones-fill')
      if (map.getLayer('stage-zones-line')) map.moveLayer('stage-zones-line')
      if (map.getLayer('stage-zone-draft-line')) map.moveLayer('stage-zone-draft-line')
      if (map.getLayer('stage-zone-draft-vertices')) map.moveLayer('stage-zone-draft-vertices')
    }

    return runWhenMapReady(map, mapLoadedRef.current, updateStageZones)
  }, [stageZones, stageZoneDraft])

  // ── Status zone layers update ──────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current
    if (!map) return undefined

    const updateStatusZones = () => {
      ensureStatusZoneLayers(map)
      map.getSource('status-zones-src')?.setData(statusZoneGeojson(statusZones))
      map.getSource('status-zone-draft-src')?.setData(stageDraftGeojson(statusZoneDraft))
      if (map.getLayer('status-zones-fill')) map.moveLayer('status-zones-fill')
      if (map.getLayer('status-zones-line')) map.moveLayer('status-zones-line')
      if (map.getLayer('status-zone-draft-line')) map.moveLayer('status-zone-draft-line')
      if (map.getLayer('status-zone-draft-vertices')) map.moveLayer('status-zone-draft-vertices')
    }

    return runWhenMapReady(map, mapLoadedRef.current, updateStatusZones)
  }, [statusZones, statusZoneDraft])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return undefined

    const updateManagementZones = () => {
      ensureManagementZoneLayers(map)
      map.getSource('management-zones-src')?.setData(managementZoneGeojson(managementZones))
      map.getSource('management-zone-draft-src')?.setData(stageDraftGeojson(managementZoneDraft))
      if (map.getLayer('management-zones-fill')) map.moveLayer('management-zones-fill')
      if (map.getLayer('management-zones-line')) map.moveLayer('management-zones-line')
      if (map.getLayer('management-zone-draft-line')) map.moveLayer('management-zone-draft-line')
      if (map.getLayer('management-zone-draft-vertices')) map.moveLayer('management-zone-draft-vertices')
    }

    return runWhenMapReady(map, mapLoadedRef.current, updateManagementZones)
  }, [managementZones, managementZoneDraft])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return undefined

    const updateCecidZones = () => {
      ensureCecidZoneLayers(map)
      map.getSource('cecid-zones-src')?.setData(cecidZoneGeojson(
        cecidWeedZones,
        legacyCecidEmergenceZones,
      ))
      map.getSource('cecid-zone-draft-src')?.setData(stageDraftGeojson(cecidZoneDraft))
      if (map.getLayer('cecid-zones-fill')) map.moveLayer('cecid-zones-fill')
      if (map.getLayer('cecid-zones-line')) map.moveLayer('cecid-zones-line')
      if (map.getLayer('cecid-zone-draft-line')) map.moveLayer('cecid-zone-draft-line')
      if (map.getLayer('cecid-zone-draft-vertices')) map.moveLayer('cecid-zone-draft-vertices')
    }

    return runWhenMapReady(map, mapLoadedRef.current, updateCecidZones)
  }, [cecidWeedZones, legacyCecidEmergenceZones, cecidZoneDraft])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return undefined
    const applyVisibility = () => {
      const groups = {
        stage: ['stage-zones-fill', 'stage-zones-line'],
        status: ['status-zones-fill', 'status-zones-line'],
        management: ['management-zones-fill', 'management-zones-line'],
        cecid: ['cecid-zones-fill', 'cecid-zones-line'],
      }
      Object.entries(groups).forEach(([type, layers]) => {
        layers.forEach((layer) => {
          if (map.getLayer(layer)) {
            map.setLayoutProperty(layer, 'visibility', zoneVisibility[type] === false ? 'none' : 'visible')
          }
        })
      })
    }
    return runWhenMapReady(map, mapLoadedRef.current, applyVisibility)
  }, [zoneVisibility])

  // ── Status zone drawing interaction ──────────────────────────────────
  useEffect(() => {
    const map = mapRef.current
    if (!map) return undefined

    const active = [
      { drawing: stageZoneDrawing, onClick: onStageZoneMapClick, onDraftChange: onStageZoneDraftChange },
      { drawing: statusZoneDrawing, onClick: onStatusZoneMapClick, onDraftChange: onStatusZoneDraftChange },
      { drawing: managementZoneDrawing, onClick: onManagementZoneMapClick, onDraftChange: onManagementZoneDraftChange },
      { drawing: cecidZoneDrawing, onClick: onCecidZoneMapClick, onDraftChange: onCecidZoneDraftChange },
    ].find((candidate) => candidate.drawing)
    if (!active) return undefined

    const canvas = map.getCanvas()
    const previousCursor = canvas.style.cursor
    canvas.style.cursor = 'crosshair'
    map.doubleClickZoom.disable()

    if (zoneDrawMode !== 'lasso') {
      const handleMapClick = (event) => {
        active.onClick?.([event.lngLat.lng, event.lngLat.lat])
      }
      map.on('click', handleMapClick)
      return () => {
        map.off('click', handleMapClick)
        map.doubleClickZoom.enable()
        canvas.style.cursor = previousCursor
      }
    }

    let dragging = false
    let lassoCoordinates = []
    let lastScreenPoint = null

    const publishDraft = () => {
      active.onDraftChange?.(simplifyLassoCoordinates(lassoCoordinates))
    }
    const handleMouseDown = (event) => {
      if (event.originalEvent?.button != null && event.originalEvent.button !== 0) return
      dragging = true
      lassoCoordinates = [[event.lngLat.lng, event.lngLat.lat]]
      lastScreenPoint = event.point
      map.dragPan.disable()
      event.preventDefault?.()
      publishDraft()
    }
    const handleMouseMove = (event) => {
      if (!dragging) return
      const dx = event.point.x - lastScreenPoint.x
      const dy = event.point.y - lastScreenPoint.y
      if (Math.hypot(dx, dy) < 3) return
      lastScreenPoint = event.point
      lassoCoordinates.push([event.lngLat.lng, event.lngLat.lat])
      publishDraft()
    }
    const finishLasso = (event) => {
      if (!dragging) return
      if (event?.lngLat) lassoCoordinates.push([event.lngLat.lng, event.lngLat.lat])
      dragging = false
      active.onDraftChange?.(simplifyLassoCoordinates(lassoCoordinates))
      map.dragPan.enable()
    }

    map.on('mousedown', handleMouseDown)
    map.on('mousemove', handleMouseMove)
    map.on('mouseup', finishLasso)
    window.addEventListener('mouseup', finishLasso)

    return () => {
      map.off('mousedown', handleMouseDown)
      map.off('mousemove', handleMouseMove)
      map.off('mouseup', finishLasso)
      window.removeEventListener('mouseup', finishLasso)
      map.dragPan.enable()
      map.doubleClickZoom.enable()
      canvas.style.cursor = previousCursor
    }
  }, [
    cecidZoneDrawing,
    managementZoneDrawing,
    onCecidZoneDraftChange,
    onCecidZoneMapClick,
    onManagementZoneDraftChange,
    onManagementZoneMapClick,
    onStageZoneDraftChange,
    onStageZoneMapClick,
    onStatusZoneDraftChange,
    onStatusZoneMapClick,
    stageZoneDrawing,
    statusZoneDrawing,
    zoneDrawMode,
  ])

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

  }, [points, alerts, onTreeClick])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return undefined
    const timers = []

    const fitSelectedOrchard = () => {
      map.resize()
      const contentBounds = reportMode
        ? reportContentBounds(fitPoints, [fitZones])
        : null
      if (fitMapToBounds(map, contentBounds, 0, REPORT_FIT_PADDING)) return

      const overlayBounds = fitToOrthophoto && activeOverlay
        ? imageCoordinateBounds(activeOverlay.coordinates)
        : null
      if (fitMapToBounds(map, overlayBounds, reportMode ? 0 : 450)) return

      if (fitPoints.length === 1) {
        map.easeTo({ center: [fitPoints[0].lon, fitPoints[0].lat], zoom: DEFAULT_ZOOM, duration: reportMode ? 0 : 350 })
        return
      }

      fitMapToBounds(map, pointBounds(fitPoints), reportMode ? 0 : 450)
    }

    const runFitSequence = () => {
      fitSelectedOrchard()
      if (reportMode) return
      timers.push(window.setTimeout(fitSelectedOrchard, 150))
      timers.push(window.setTimeout(fitSelectedOrchard, 450))
    }

    const cleanup = runWhenMapReady(map, mapLoadedRef.current, runFitSequence)

    return () => {
      cleanup()
      timers.forEach((timer) => window.clearTimeout(timer))
    }
  }, [
    viewportKey,
    activeOverlay,
    fitToOrthophoto,
    fitPoints,
    reportMode,
    fitZones,
  ])

  // ── Heatmap data update ────────────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current
    if (!map) return undefined

    heatmapPendingRef.current = true
    const ready = () => { heatmapPendingRef.current = false }
    const setHeatmapData = () => {
      map.once('render', ready)
      applyRiskSurfaceCanvas(map, heatmapSurface)
      if (!heatmapSurface) ready()
    }
    const cleanup = runWhenMapReady(map, mapLoadedRef.current, setHeatmapData)
    return () => { cleanup(); map.off('render', ready) }
  }, [heatmapSurface])

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

    const cleanup = runWhenMapReady(map, mapLoadedRef.current, updateGrid)

    return () => {
      cleanup()
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
      {overlayLoading && (
        <div className="risk-map-overlay-loading" role="status" aria-live="polite">
          <span className="spinner-border spinner-border-sm me-2" aria-hidden="true" />
          Loading orchard imagery…
        </div>
      )}
    </div>
  )
})
