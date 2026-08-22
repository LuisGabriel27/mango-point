import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import Navbar from '../components/Navbar'
import Sidebar from '../components/Sidebar'
import LiveMapTab from '../components/tabs/LiveMapTab'
import OverviewTab from '../components/tabs/OverviewTab'
import CropImpactTab from '../components/tabs/CropImpactTab'
import SurveillanceTab from '../components/tabs/SurveillanceTab'
import SimulationHistoryTab from '../components/tabs/SimulationHistoryTab'
import api from '../api'
import { saveSimulationRunToHistory } from '../utils/simulationHistoryStore'
import { buildGuidedBlocks, createDefaultWeatherTimeline } from '../utils/weatherSchedule'
import {
  normalizeCecidWeedZones,
  saveCecidWeedZones,
} from '../utils/cecidWeedZones'
import {
  DEFAULT_SIDEBAR_WORKFLOW,
  parseStoredSidebarCollapsed,
  sidebarWorkflowForEvent,
} from '../utils/sidebarWorkspace'
import guimarasWondersFarmTrees from '../assets/guimaras-wonders-farm-trees.json'
import {
  GUIMARAS_WONDERS_FARM_ID,
  GUIMARAS_WONDERS_FARM_OVERLAY_COORDINATES,
  mergeBundledOrchards,
} from '../utils/bundledOrchards'

const DEFAULT_ORCHARD_ID = 'default-orchard'
const DEFAULT_ORCHARD_LABEL = 'Default Orchard (BPI)'
const SELECTED_ORCHARD_STORAGE_KEY = 'mangopoint.selectedOrchardId.v1'
const SIDEBAR_COLLAPSED_STORAGE_KEY = 'mangopoint.sidebarCollapsed.v1'

const GUIMARAS_WONDERS_FARM_ORCHARD = {
  orchard_id: GUIMARAS_WONDERS_FARM_ID,
  name: 'Guimaras Wonders Farm',
  location: 'Guimaras, Philippines',
  tree_count: guimarasWondersFarmTrees.features.length,
  geojson: guimarasWondersFarmTrees,
  centroid_lon: 122.61253175014424,
  centroid_lat: 10.631031789835638,
  orthophoto_bounds: [
    122.61086363208625,
    10.629772719131637,
    122.61419986820223,
    10.63229086053964,
  ],
  orthophoto_coordinates: GUIMARAS_WONDERS_FARM_OVERLAY_COORDINATES,
  description: 'Bundled Guimaras Wonders Farm orchard map.',
  is_active: true,
  monitoring_enabled: true,
  orchard_stage: 'mature',
  days_since_flowering: 60,
  monitored_pest_types: ['cecid', 'fruitfly'],
  cecid_weed_zones: [],
}

const DEFAULT_MANUAL_WEATHER = {
  temperature_c: 30,
  wind_speed_ms: 2,
  wind_direction_deg: 90,
  rainfall_mm: 0,
  humidity: 75,
}

const fallbackTreeGeojson = { type: 'FeatureCollection', features: [] }

function readStoredSelectedOrchardId() {
  if (typeof window === 'undefined') return DEFAULT_ORCHARD_ID
  try {
    return window.localStorage.getItem(SELECTED_ORCHARD_STORAGE_KEY) || DEFAULT_ORCHARD_ID
  } catch (_) {
    return DEFAULT_ORCHARD_ID
  }
}

function writeStoredSelectedOrchardId(orchardId) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(SELECTED_ORCHARD_STORAGE_KEY, orchardId || DEFAULT_ORCHARD_ID)
  } catch (_) {
    /* ignore */
  }
}

function readStoredSidebarCollapsed() {
  if (typeof window === 'undefined') return false
  try {
    return parseStoredSidebarCollapsed(window.localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY))
  } catch (_) {
    return false
  }
}

function writeStoredSidebarCollapsed(collapsed) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, String(Boolean(collapsed)))
  } catch (_) {
    /* ignore */
  }
}

const PHENOLOGY_STAGE_OPTIONS = [
  { label: 'Dormant', value: 'dormant' },
  { label: 'Flowering', value: 'flowering' },
  { label: 'Fruitlet', value: 'fruitlet' },
  { label: 'Mature', value: 'mature' },
]

const STATUS_ZONE_OPTIONS = [
  { label: 'Healthy', value: 'healthy' },
  { label: 'Infected', value: 'infected' },
  { label: 'Bagged (reduced risk)', value: 'bagged' },
  { label: 'Dead (removed)', value: 'dead' },
  { label: 'History Infected', value: 'history_infected' },
  { label: 'Suspect (monitoring)', value: 'suspect' },
]

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
  if (geometry.type === 'Polygon') {
    const ring = geometry.coordinates?.[0] || []
    const openRing = ring.length > 1 && ring[0]?.[0] === ring.at(-1)?.[0] && ring[0]?.[1] === ring.at(-1)?.[1]
      ? ring.slice(0, -1)
      : ring
    return averageCoordinates(openRing)
  }
  return null
}

function treePointsFromGeojson(geojson) {
  const features = Array.isArray(geojson?.features) ? geojson.features : []
  return features
    .map((feature) => {
      const center = geometryCenter(feature.geometry)
      if (!center) return null
      const props = feature.properties || {}
      const treeId = props.tree_id ?? props.Tree_ID ?? props.fid ?? feature.id
      if (treeId == null) return null
      return { tree_id: String(treeId), lon: center[0], lat: center[1] }
    })
    .filter(Boolean)
}

function pointInPolygon(point, polygon) {
  if (!Array.isArray(polygon) || polygon.length < 3) return false
  const [x, y] = point
  let inside = false
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [xi, yi] = polygon[i]
    const [xj, yj] = polygon[j]
    const intersects = ((yi > y) !== (yj > y))
      && (x < ((xj - xi) * (y - yi)) / ((yj - yi) || Number.EPSILON) + xi)
    if (intersects) inside = !inside
  }
  return inside
}

function parseMaybeJson(value, fallback) {
  if (value == null) return fallback
  if (typeof value !== 'string') return value
  try {
    return JSON.parse(value)
  } catch (_) {
    return fallback
  }
}

function normalizeStageZones(value) {
  const zones = parseMaybeJson(value, [])
  if (!Array.isArray(zones)) return []
  return zones
    .map((zone, index) => {
      const coordinates = parseMaybeJson(zone?.coordinates, [])
      if (!Array.isArray(coordinates) || coordinates.length < 3) return null
      return {
        id: zone.id ?? `restored-stage-zone-${index + 1}`,
        stage: zone.stage ?? 'mature',
        coordinates,
        tree_count: zone.tree_count ?? 0,
      }
    })
    .filter(Boolean)
}

function normalizeCecidEmergenceZones(value) {
  const zones = parseMaybeJson(value, [])
  if (!Array.isArray(zones)) return []
  return zones
    .map((zone, index) => {
      const coordinates = parseMaybeJson(zone?.coordinates, [])
      if (!Array.isArray(coordinates) || coordinates.length < 3) return null
      const pressure = ['low', 'medium', 'high'].includes(String(zone?.pressure).toLowerCase())
        ? String(zone.pressure).toLowerCase()
        : 'medium'
      return {
        id: zone.id ?? `restored-cecid-zone-${index + 1}`,
        label: zone.label || `Suspected soil habitat ${index + 1}`,
        pressure,
        coordinates,
        tree_count: zone.tree_count ?? 0,
      }
    })
    .filter(Boolean)
}

function convexHull(points) {
  const sorted = [...points]
    .map((point) => [Number(point[0]), Number(point[1])])
    .filter(([x, y]) => Number.isFinite(x) && Number.isFinite(y))
    .sort((a, b) => (a[0] - b[0]) || (a[1] - b[1]))
  if (sorted.length <= 1) return sorted

  const cross = (origin, a, b) => (
    (a[0] - origin[0]) * (b[1] - origin[1])
    - (a[1] - origin[1]) * (b[0] - origin[0])
  )
  const lower = []
  for (const point of sorted) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], point) <= 0) {
      lower.pop()
    }
    lower.push(point)
  }
  const upper = []
  for (let i = sorted.length - 1; i >= 0; i -= 1) {
    const point = sorted[i]
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], point) <= 0) {
      upper.pop()
    }
    upper.push(point)
  }
  return lower.slice(0, -1).concat(upper.slice(0, -1))
}

function paddedBoundsPolygon(points) {
  if (!points.length) return []
  const lons = points.map((point) => point[0])
  const lats = points.map((point) => point[1])
  const minLon = Math.min(...lons)
  const maxLon = Math.max(...lons)
  const minLat = Math.min(...lats)
  const maxLat = Math.max(...lats)
  const padLon = Math.max((maxLon - minLon) * 0.08, 0.00003)
  const padLat = Math.max((maxLat - minLat) * 0.08, 0.00003)
  return [
    [minLon - padLon, minLat - padLat],
    [maxLon + padLon, minLat - padLat],
    [maxLon + padLon, maxLat + padLat],
    [minLon - padLon, maxLat + padLat],
  ]
}

function stageZonesFromOverrides(stageOverrides, treePoints) {
  const overrides = parseMaybeJson(stageOverrides, {})
  if (!overrides || typeof overrides !== 'object') return []

  const pointsById = new Map(treePoints.map((point) => [String(point.tree_id), point]))
  const byStage = new Map()
  for (const [treeId, stage] of Object.entries(overrides)) {
    const point = pointsById.get(String(treeId))
    if (!point || !stage) continue
    const stageKey = String(stage)
    if (!byStage.has(stageKey)) byStage.set(stageKey, [])
    byStage.get(stageKey).push([point.lon, point.lat])
  }

  return [...byStage.entries()].map(([stage, points], index) => {
    const hull = convexHull(points)
    const coordinates = hull.length >= 3 ? hull : paddedBoundsPolygon(points)
    if (coordinates.length < 3) return null
    return {
      id: `restored-${stage}-zone-${index + 1}`,
      stage,
      coordinates,
      tree_count: points.length,
      source: 'tree_stage_overrides',
    }
  }).filter(Boolean)
}

function stageOverridesFromZones(zones, treePoints) {
  const overrides = {}

  for (const zone of zones || []) {
    const coordinates = Array.isArray(zone?.coordinates) ? zone.coordinates : []
    if (coordinates.length < 3 || !zone?.stage) continue

    for (const point of treePoints) {
      if (pointInPolygon([point.lon, point.lat], coordinates)) {
        overrides[point.tree_id] = zone.stage
      }
    }
  }

  return overrides
}

function isActiveAlert(alert) {
  return String(alert?.status ?? '').toLowerCase() === 'active'
}

function isConditionAlert(alert) {
  const zone = String(alert?.zone_name ?? '').toLowerCase()
  return zone.includes('weather forecast') || zone.includes('gate condition')
}

function isOrchardAlert(alert, orchardId) {
  return String(alert?.orchard_id ?? '') === String(orchardId)
}

function isCurrentSimulationRiskAlert(alert, runId) {
  return Boolean(runId)
    && isActiveAlert(alert)
    && !isConditionAlert(alert)
    && String(alert?.simulation_run_id ?? '') === String(runId)
}

export default function DashboardPage() {
  const [activeTab, setActiveTab] = useState('live-map')
  const [sidebarWorkflow, setSidebarWorkflow] = useState(DEFAULT_SIDEBAR_WORKFLOW)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(readStoredSidebarCollapsed)
  const [sidebarMobileOpen, setSidebarMobileOpen] = useState(false)
  const [suggestedSimParams, setSuggestedSimParams] = useState(null)

  // Orchard state
  const [orchards, setOrchards] = useState(() => (
    mergeBundledOrchards([], GUIMARAS_WONDERS_FARM_ORCHARD)
  ))
  const [selectedOrchardId, setSelectedOrchardId] = useState(readStoredSelectedOrchardId)
  const selectedOrchardIdRef = useRef(selectedOrchardId)
  const [orchardLoading, setOrchardLoading] = useState(false)

  // Simulation / map state
  const [simData, setSimData] = useState(null)
  const [treeOverrides, setTreeOverrides] = useState({})
  const [treeStageOverrides, setTreeStageOverrides] = useState({})
  const [phenologyZones, setPhenologyZones] = useState([])
  const [stageZoneDrawing, setStageZoneDrawing] = useState(false)
  const [stageZoneStage, setStageZoneStage] = useState('mature')
  const [stageZoneDraft, setStageZoneDraft] = useState([])
  const [playbackFrames, setPlaybackFrames] = useState([])
  const [currentFrameIdx, setCurrentFrameIdx] = useState(0)
  const [mapRefreshKey, setMapRefreshKey] = useState(0)
  const [simulationTemplate, setSimulationTemplate] = useState(null)
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0)
  const [selectedPestType, setSelectedPestType] = useState('fruitfly')

  // Status zone drawing (bulk status change)
  const [statusZoneDrawing, setStatusZoneDrawing] = useState(false)
  const [statusZoneStatus, setStatusZoneStatus] = useState('infected')
  const [statusZoneDraft, setStatusZoneDraft] = useState([])
  const [statusZones, setStatusZones] = useState([])

  // Persistent orchard weed habitat plus read-only legacy soil-source assumptions.
  const [cecidWeedZones, setCecidWeedZones] = useState([])
  const [legacyCecidEmergenceZones, setLegacyCecidEmergenceZones] = useState([])
  const [cecidZoneDrawing, setCecidZoneDrawing] = useState(false)
  const [cecidZoneDensity, setCecidZoneDensity] = useState('moderate')
  const [cecidZoneLabel, setCecidZoneLabel] = useState('Weed habitat')
  const [cecidZoneDraft, setCecidZoneDraft] = useState([])
  const [cecidZoneEditingId, setCecidZoneEditingId] = useState(null)
  const [cecidZoneSaveState, setCecidZoneSaveState] = useState('idle')
  const [cecidZoneSaveError, setCecidZoneSaveError] = useState('')
  const weedSaveVersionRef = useRef(0)

  // Unified zone action history (tracks order of stage/status zone saves)
  const [zoneHistory, setZoneHistory] = useState([])

  // Monitoring state
  const [monitoringData, setMonitoringData] = useState(null)

  // Alerts
  const [alerts, setAlerts] = useState([])
  const [alertLoading, setAlertLoading] = useState(false)

  // Weather
  const [weather, setWeather] = useState(null)
  const [manualWeather, setManualWeather] = useState(DEFAULT_MANUAL_WEATHER)
  const [weatherOverrideActive, setWeatherOverrideActive] = useState(false)
  const [weatherTimeline, setWeatherTimeline] = useState(createDefaultWeatherTimeline)

  // Tree management modal
  const [selectedTree, setSelectedTree] = useState(null)

  // Fallback GeoJSON from static file (mirrors Python app's DEFAULT_ORCHARD)
  const [fallbackGeojson, setFallbackGeojson] = useState(fallbackTreeGeojson)
  useEffect(() => {
    selectedOrchardIdRef.current = selectedOrchardId
  }, [selectedOrchardId])

  useEffect(() => {
    fetch('/trees.geojson')
      .then((r) => {
        if (!r.ok) throw new Error(`Unable to load trees.geojson (${r.status})`)
        return r.json()
      })
      .then((data) => setFallbackGeojson(data))
      .catch(() => setFallbackGeojson(fallbackTreeGeojson))
  }, [])

  // ── Helpers ──────────────────────────────────────────────────────────
  const selectedOrchardRecord = orchards.find((o) => o.orchard_id === selectedOrchardId) ?? null
  const orchardGeojson = selectedOrchardRecord?.geojson ?? fallbackGeojson

  const orchardName = selectedOrchardRecord?.name ?? DEFAULT_ORCHARD_LABEL
  const orchardTreePoints = useMemo(
    () => treePointsFromGeojson(orchardGeojson),
    [orchardGeojson],
  )
  const orchardWeatherCoordinates = useMemo(() => {
    const recordLat = Number(selectedOrchardRecord?.centroid_lat)
    const recordLon = Number(selectedOrchardRecord?.centroid_lon)
    if (Number.isFinite(recordLat) && Number.isFinite(recordLon)) {
      return { lat: recordLat, lon: recordLon }
    }
    if (orchardTreePoints.length) {
      return {
        lat: orchardTreePoints.reduce((sum, point) => sum + point.lat, 0) / orchardTreePoints.length,
        lon: orchardTreePoints.reduce((sum, point) => sum + point.lon, 0) / orchardTreePoints.length,
      }
    }
    return { lat: 10.585, lon: 122.58 }
  }, [orchardTreePoints, selectedOrchardRecord?.centroid_lat, selectedOrchardRecord?.centroid_lon])
  // IMPORTANT: depend on the primitive URL + serialized coordinates instead
  // of `selectedOrchardRecord`. Every `Refresh Orchards` click rebuilds the
  // orchard list, so the record object identity changes even when the
  // orthophoto did not — and the previous version of this memo invalidated
  // on every refresh, which cancelled the in-flight image download for
  // GWF and forced the fetch to restart from zero on each click. Comparing
  // by value lets the existing download finish instead of restarting it.
  const orthoUrl = selectedOrchardRecord?.orthophoto_url ?? null
  const orthoCoordinatesKey = useMemo(
    () => (selectedOrchardRecord?.orthophoto_coordinates
      ? JSON.stringify(selectedOrchardRecord.orthophoto_coordinates)
      : null),
    [selectedOrchardRecord?.orthophoto_coordinates],
  )
  const orchardOrthophoto = useMemo(
    () => (
      orthoUrl && orthoCoordinatesKey
        ? { url: orthoUrl, coordinates: JSON.parse(orthoCoordinatesKey) }
        : null
    ),
    [orthoUrl, orthoCoordinatesKey],
  )
  const selectedOrchardWeedZonesKey = useMemo(
    () => JSON.stringify(selectedOrchardRecord?.cecid_weed_zones ?? []),
    [selectedOrchardRecord?.cecid_weed_zones],
  )

  useEffect(() => {
    setCecidWeedZones(normalizeCecidWeedZones(selectedOrchardRecord?.cecid_weed_zones))
    setLegacyCecidEmergenceZones([])
    setCecidZoneEditingId(null)
    setCecidZoneSaveState('idle')
    setCecidZoneSaveError('')
  }, [selectedOrchardId, selectedOrchardWeedZonesKey])

  // Displayed geojson: current playback frame, or final sim snapshot, or null
  const currentFrame = playbackFrames.length > 0 ? (playbackFrames[currentFrameIdx] ?? null) : null
  const mapGeojson = currentFrame?.risk_geojson ?? simData?.risk_geojson ?? null

  const activeOrchardAlerts = useMemo(
    () => alerts.filter((alert) => isOrchardAlert(alert, selectedOrchardId)),
    [alerts, selectedOrchardId],
  )
  const currentSimulationRunId = simData?.run_id ?? simData?.metadata?.run_id ?? null
  const mapAlerts = useMemo(
    () => activeOrchardAlerts.filter((alert) => (
      isCurrentSimulationRiskAlert(alert, currentSimulationRunId)
    )),
    [activeOrchardAlerts, currentSimulationRunId],
  )

  // Build decision support metrics from simulation data
  // (SimulationResponse has no dedicated decision_support field — compute it here)
  const decisionMetrics = useMemo(() => {
    if (!simData?.risk_geojson) return null
    const features = simData.risk_geojson?.features ?? []
    const total = features.length
    if (!total) return null

    const zone1 = features.filter((f) => (f.properties?.risk ?? 0) < 0.2).length
    const zone2 = features.filter((f) => { const r = f.properties?.risk ?? 0; return r >= 0.2 && r < 0.6 }).length
    const zone3 = features.filter((f) => (f.properties?.risk ?? 0) >= 0.6).length

    const z1 = zone1 / total, z2 = zone2 / total, z3 = zone3 / total
    const peak = simData.peak_risk ?? 0
    const nInfested = simData.n_infested_final ?? 0
    const pestReduction = z3 < 0.3 ? 0.45 : z3 < 0.6 ? 0.25 : 0.10
    const savings = total * 180 * pestReduction

    const actions = []
    if (z3 > 0.02) actions.push({
      title: 'Apply targeted treatment to high-risk trees',
      timing: peak >= 0.75 ? 'Immediately (within 24 h)' : 'Within 48 hours',
      priority: peak >= 0.75 ? 'Urgent' : 'High',
      scope_label: `Zone 3 — ${(z3 * 100).toFixed(0)}% of orchard`,
      max_risk: peak,
      recommended_steps: [
        'Mark and bag high-risk trees from the Live Map',
        'Apply pesticide spray per recommended schedule',
        'Monitor treated trees daily for 7 days',
      ],
    })
    if (z2 > 0.05) actions.push({
      title: 'Increase monitoring in moderate-risk zone',
      timing: 'Starting today',
      priority: 'Medium',
      scope_label: `Zone 2 — ${(z2 * 100).toFixed(0)}% of orchard`,
      max_risk: 0.45,
      recommended_steps: [
        'Install or inspect pheromone traps in Zone 2',
        'Visual inspection every 3 days',
        'Log observations in MangoPoint',
      ],
    })
    if (z1 > 0.3) actions.push({
      title: 'Maintain preventive measures in safe zone',
      timing: 'Routine',
      priority: 'Low',
      scope_label: `Zone 1 — ${(z1 * 100).toFixed(0)}% of orchard`,
      max_risk: 0.15,
      recommended_steps: [
        'Continue bagging program for susceptible trees',
        'Sanitation of fallen fruit',
        'Weekly inspection',
      ],
    })

    const summary =
      peak >= 0.75 ? 'Critical risk — immediate field action required to prevent spread.' :
      peak >= 0.5  ? 'High risk — targeted treatment recommended within 48 hours.' :
      peak >= 0.25 ? 'Moderate risk — increase monitoring and prepare treatment resources.' :
                     'Low pest risk — continue current prevention measures.'

    return {
      zones: { zone_1_pct: z1, zone_2_pct: z2, zone_3_pct: z3 },
      economic: { pesticide_reduction: pestReduction, estimated_savings: savings },
      action_plan: actions,
      summary_message: summary,
    }
  }, [simData])

  // ── Data fetchers ─────────────────────────────────────────────────────
  const selectOrchardId = useCallback((orchardId) => {
    const nextOrchardId = orchardId || DEFAULT_ORCHARD_ID
    selectedOrchardIdRef.current = nextOrchardId
    setSelectedOrchardId(nextOrchardId)
    writeStoredSelectedOrchardId(nextOrchardId)
  }, [])

  const fetchAlerts = useCallback(async () => {
    setAlertLoading(true)
    try {
      const orchardId = selectedOrchardIdRef.current || DEFAULT_ORCHARD_ID
      const res = await api.getAlerts({ limit: 100, orchard_id: orchardId })
      setAlerts(res.data.alerts ?? [])
    } catch (_) {
      /* ignore */
    } finally {
      setAlertLoading(false)
    }
  }, [])

  const fetchOrchards = useCallback(async (selectedIdOverride = selectedOrchardIdRef.current) => {
    setOrchardLoading(true)
    try {
      const res = await api.getOrchards({ active_only: true, include_geojson: true })
      const list = mergeBundledOrchards(
        res.data.orchards ?? [],
        GUIMARAS_WONDERS_FARM_ORCHARD,
      )
      setOrchards(list)
      const activeSelectedId = selectedIdOverride || DEFAULT_ORCHARD_ID
      const selectedRecord = list.find((o) => o.orchard_id === activeSelectedId)
      if (!selectedRecord && activeSelectedId !== DEFAULT_ORCHARD_ID) {
        selectOrchardId(DEFAULT_ORCHARD_ID)
      }
      // After orchards load, check the 48 h weather forecast and create
      // rain-triggered pest alerts so growers are never caught off-guard.
      const targetId = selectedRecord ? activeSelectedId : null
      if (targetId) {
        const record = selectedRecord
        api.checkWeatherForecast({
          orchard_id: targetId,
          lat: record?.centroid_lat ?? null,
          lon: record?.centroid_lon ?? null,
          orchard_stage: record?.orchard_stage ?? null,
          monitored_pest_types: record?.monitored_pest_types ?? null,
        }).then(() => fetchAlerts()).catch(() => {})
      }
    } catch (_) {
      // Backend may be offline; keep existing orchard list
    } finally {
      setOrchardLoading(false)
    }
  }, [fetchAlerts, selectOrchardId])

  const persistCecidWeedZones = useCallback(async (nextZones) => {
    const orchardId = selectedOrchardIdRef.current || DEFAULT_ORCHARD_ID
    const normalized = normalizeCecidWeedZones(nextZones)
    const saveVersion = weedSaveVersionRef.current + 1
    weedSaveVersionRef.current = saveVersion
    setCecidWeedZones(normalized)
    setCecidZoneSaveState('saving')
    setCecidZoneSaveError('')

    const outcome = await saveCecidWeedZones(orchardId, normalized, api.updateOrchard)
    if (weedSaveVersionRef.current !== saveVersion || selectedOrchardIdRef.current !== orchardId) return
    if (!outcome.ok) {
      setCecidZoneSaveState('error')
      setCecidZoneSaveError(outcome.message)
      return
    }
    const savedRecord = outcome.response.data
    setCecidWeedZones(outcome.zones)
    setOrchards((current) => current.map((record) => (
      record.orchard_id === orchardId ? { ...record, ...savedRecord } : record
    )))
    setCecidZoneSaveState('saved')
  }, [])

  const retryCecidWeedZoneSave = useCallback(() => {
    persistCecidWeedZones(cecidWeedZones)
  }, [cecidWeedZones, persistCecidWeedZones])

  const handleOrchardUpload = useCallback(async ({ name, treeGeojson, orthophoto, dtm, dsm }) => {
    const formData = new FormData()
    formData.append('name', name)
    formData.append('tree_geojson', treeGeojson)
    formData.append('orthophoto', orthophoto)
    if (dtm) formData.append('dtm', dtm)
    if (dsm) formData.append('dsm', dsm)

    const res = await api.uploadOrchard(formData)
    const uploaded = res.data
    setOrchards((prev) => {
      const others = prev.filter((o) => o.orchard_id !== uploaded.orchard_id)
      return [...others, uploaded].sort((a, b) => String(a.name).localeCompare(String(b.name)))
    })
    selectOrchardId(uploaded.orchard_id)
    setSimData(null)
    setTreeOverrides({})
    setTreeStageOverrides({})
    setPhenologyZones([])
    setStageZoneDrawing(false)
    setStageZoneDraft([])
    setStatusZones([])
    setStatusZoneDrawing(false)
    setStatusZoneDraft([])
    setCecidWeedZones(normalizeCecidWeedZones(uploaded.cecid_weed_zones))
    setLegacyCecidEmergenceZones([])
    setCecidZoneDrawing(false)
    setCecidZoneDraft([])
    setCecidZoneEditingId(null)
    setPlaybackFrames([])
    setCurrentFrameIdx(0)
    setMapRefreshKey((value) => value + 1)
    fetchAlerts()
    return uploaded
  }, [fetchAlerts, selectOrchardId])

  const handleOrchardSelect = useCallback((orchardId) => {
    selectOrchardId(orchardId)
    setSimData(null)
    setTreeOverrides({})
    setTreeStageOverrides({})
    setPhenologyZones([])
    setStageZoneDrawing(false)
    setStageZoneDraft([])
    setStatusZones([])
    setStatusZoneDrawing(false)
    setStatusZoneDraft([])
    setCecidWeedZones([])
    setLegacyCecidEmergenceZones([])
    setCecidZoneDrawing(false)
    setCecidZoneDraft([])
    setCecidZoneEditingId(null)
    setPlaybackFrames([])
    setCurrentFrameIdx(0)
    setMapRefreshKey((value) => value + 1)
    fetchAlerts()
  }, [fetchAlerts, selectOrchardId])

  const handleOrchardRefresh = useCallback(async () => {
    // Clear all simulation and alert state for a fresh start
    setSimData(null)
    setTreeOverrides({})
    setTreeStageOverrides({})
    setPhenologyZones([])
    setStageZoneDrawing(false)
    setStageZoneDraft([])
    setStatusZones([])
    setStatusZoneDrawing(false)
    setStatusZoneDraft([])
    setCecidWeedZones([])
    setLegacyCecidEmergenceZones([])
    setCecidZoneDrawing(false)
    setCecidZoneDraft([])
    setCecidZoneEditingId(null)
    setPlaybackFrames([])
    setCurrentFrameIdx(0)
    setSimulationTemplate(null)
    setZoneHistory([])
    setSelectedTree(null)
    setAlerts([])

    // Clear server-side in-memory alerts
    try { await api.clearAlerts() } catch (_) { /* ignore */ }

    // Re-fetch orchards and alerts fresh
    await fetchOrchards(selectedOrchardIdRef.current)
    setMapRefreshKey((value) => value + 1)
    setHistoryRefreshKey((key) => key + 1)
    fetchAlerts()
  }, [fetchOrchards, fetchAlerts])

  const fetchWeather = useCallback(async (bypassCache = false) => {
    try {
      const res = await api.getLiveWeather({
        lat: orchardWeatherCoordinates.lat,
        lon: orchardWeatherCoordinates.lon,
        bypass_cache: Boolean(bypassCache),
      })
      setWeather(res.data)
    } catch (_) { /* ignore */ }
  }, [orchardWeatherCoordinates.lat, orchardWeatherCoordinates.lon])

  const fetchMonitoring = useCallback(async () => {
    try {
      const res = await api.getMonitoringMetrics()
      setMonitoringData(res.data)
    } catch (_) { /* ignore */ }
  }, [])

  // ── Initial loads ──────────────────────────────────────────────────────
  useEffect(() => { fetchOrchards() }, [])
  useEffect(() => { fetchAlerts() }, [])
  useEffect(() => { fetchWeather() }, [fetchWeather])
  useEffect(() => { fetchMonitoring() }, [])
  useEffect(() => { writeStoredSidebarCollapsed(sidebarCollapsed) }, [sidebarCollapsed])

  const handleSuggestedSimulation = useCallback((params) => {
    setSuggestedSimParams(params)
    setSidebarWorkflow((current) => sidebarWorkflowForEvent('alert-prefill', current))
    setSidebarCollapsed(false)
    if (typeof window.matchMedia === 'function' && window.matchMedia('(max-width: 991.98px)').matches) {
      setSidebarMobileOpen(true)
    }
  }, [])

  // ── Auto-refresh intervals ────────────────────────────────────────────
  useEffect(() => {
    const id = setInterval(fetchWeather, 60_000)
    return () => clearInterval(id)
  }, [fetchWeather])


  // ── Simulation complete handler ───────────────────────────────────────
  const applySimulationResult = useCallback((data, options = {}) => {
    setSimData(data)
    const frames = Array.isArray(data.time_series) ? data.time_series : []
    setPlaybackFrames(frames)
    setCurrentFrameIdx(options.startAtLastFrame && frames.length ? frames.length - 1 : 0)
    fetchAlerts()
    window.setTimeout(fetchAlerts, 1200)
    fetchMonitoring()
  }, [fetchAlerts, fetchMonitoring])

  const handleSimulationComplete = useCallback((data) => {
    const params = parseMaybeJson(data?.request_payload ?? data?.input_parameters, {})
    const enrichedData = {
      ...data,
      orchard_id: data?.orchard_id ?? params.orchard_id ?? selectedOrchardIdRef.current,
      request_payload: params,
      input_parameters: params,
    }

    applySimulationResult(enrichedData)
    saveSimulationRunToHistory(enrichedData)
      .catch(() => {})
      .finally(() => setHistoryRefreshKey((key) => key + 1))
    window.setTimeout(() => setHistoryRefreshKey((key) => key + 1), 1500)
  }, [applySimulationResult])

  const restoreStageContext = useCallback((params = {}, options = {}) => {
    const safeParams = parseMaybeJson(params, {})
    const dashboardState = parseMaybeJson(safeParams.dashboard_state, {})
    const savedStageOverrides = parseMaybeJson(safeParams.tree_stage_overrides, {})
    const savedZones = normalizeStageZones(
      dashboardState.phenology_zones ?? safeParams.phenology_zones,
    )
    const restoredCecidWeedZones = normalizeCecidWeedZones(
      safeParams.cecid_weed_zones ?? dashboardState.cecid_weed_zones,
    )
    const restoredLegacyCecidZones = normalizeCecidEmergenceZones(
      safeParams.cecid_emergence_zones ?? dashboardState.cecid_emergence_zones,
    )
    const restoredZones = savedZones.length
      ? savedZones
      : stageZonesFromOverrides(savedStageOverrides, orchardTreePoints)

    const applyRestoredStages = () => {
      setPhenologyZones(restoredZones)
      setTreeStageOverrides(savedStageOverrides)
      setStageZoneDraft([])
      setStageZoneDrawing(false)
      setCecidWeedZones(restoredCecidWeedZones)
      setLegacyCecidEmergenceZones(restoredLegacyCecidZones)
      setCecidZoneDraft([])
      setCecidZoneEditingId(null)
      setCecidZoneDrawing(false)
      setZoneHistory([
        ...restoredZones.map(() => ({ type: 'stage' })),
        ...restoredCecidWeedZones.map((zone) => ({ type: 'cecid', id: zone.id })),
      ])
      setMapRefreshKey((value) => value + 1)
    }

    if (options.defer) {
      setPhenologyZones([])
      setTreeStageOverrides({})
      setCecidWeedZones([])
      setLegacyCecidEmergenceZones([])
      window.setTimeout(applyRestoredStages, 0)
      return
    }

    applyRestoredStages()
  }, [orchardTreePoints])

  const restoreWeatherContext = useCallback((params = {}) => {
    const safeParams = parseMaybeJson(params, {})
    const dashboardState = parseMaybeJson(safeParams.dashboard_state, {})
    const savedTimeline = parseMaybeJson(dashboardState.weather_timeline ?? safeParams.weather_timeline, null)
    const savedBlocks = parseMaybeJson(safeParams.manual_weather_blocks, null)

    if (savedTimeline?.enabled || Array.isArray(savedBlocks) || Array.isArray(safeParams.manual_weather_series)) {
      const defaults = createDefaultWeatherTimeline()
      const restoredBlocks = savedTimeline?.mode === 'guided'
        ? buildGuidedBlocks(savedTimeline?.guided_phases || defaults.guided_phases, 168)
        : savedTimeline?.advanced_blocks || savedBlocks || defaults.advanced_blocks
      setWeatherTimeline({
        ...defaults,
        ...savedTimeline,
        enabled: true,
        mode: 'advanced',
        guided_phases: savedTimeline?.guided_phases || defaults.guided_phases,
        advanced_blocks: restoredBlocks,
        start_datetime: savedTimeline?.start_datetime || safeParams.manual_weather_start || defaults.start_datetime,
      })
      setWeatherOverrideActive(true)
      return
    }

    if (safeParams.manual_weather) {
      const savedWeather = safeParams.manual_weather
      setManualWeather({
        ...DEFAULT_MANUAL_WEATHER,
        ...savedWeather,
        wind_direction_deg: savedWeather.wind_direction_deg ?? savedWeather.wind_dir_deg ?? DEFAULT_MANUAL_WEATHER.wind_direction_deg,
        sim_datetime: safeParams.manual_weather_start || savedWeather.sim_datetime || '',
      })
      setWeatherTimeline((current) => ({ ...current, enabled: false }))
      setWeatherOverrideActive(true)
      return
    }

    setWeatherTimeline((current) => ({ ...current, enabled: false }))
    setWeatherOverrideActive(false)
  }, [])

  const handleHistoricalSimulationLoad = useCallback((data) => {
    const params = parseMaybeJson(data.request_payload ?? data.input_parameters, {})
    setActiveTab('live-map')
    setSidebarWorkflow((current) => sidebarWorkflowForEvent('historical-result', current))
    setSidebarCollapsed(false)
    applySimulationResult(data, { startAtLastFrame: true })
    restoreStageContext(params, { defer: true })
    restoreWeatherContext(params)
    setSimulationTemplate({
      ...params,
      _loaded_at: Date.now(),
    })
  }, [applySimulationResult, restoreStageContext, restoreWeatherContext])

  const handleHistoricalTemplateLoad = useCallback((params) => {
    const safeParams = parseMaybeJson(params, {})
    setActiveTab('live-map')
    setSidebarWorkflow((current) => sidebarWorkflowForEvent('historical-template', current))
    setSidebarCollapsed(false)
    restoreStageContext(safeParams)
    restoreWeatherContext(safeParams)
    setSimulationTemplate({
      ...safeParams,
      _loaded_at: Date.now(),
    })
  }, [restoreStageContext, restoreWeatherContext])

  // ── Tree management modal ─────────────────────────────────────────────
  const handleTreeClick = useCallback((treeData) => {
    setSelectedTree(treeData)
  }, [])

  const applyTreeStatus = useCallback((treeId, status) => {
    setTreeOverrides((prev) => ({ ...prev, [String(treeId)]: status }))
    setSelectedTree(null)
  }, [])

  const handleStageZoneStart = useCallback(() => {
    // Cancel any active status zone drawing (mutual exclusivity)
    setStatusZoneDraft([])
    setStatusZoneDrawing(false)
    setCecidZoneDraft([])
    setCecidZoneEditingId(null)
    setCecidZoneDrawing(false)
    setStageZoneDraft([])
    setStageZoneDrawing(true)
  }, [])

  const handleStageZoneCancel = useCallback(() => {
    setStageZoneDraft([])
    setStageZoneDrawing(false)
  }, [])

  const handleStageZoneMapClick = useCallback((coordinate) => {
    setStageZoneDraft((prev) => [...prev, coordinate])
  }, [])

  const handleStageZoneUndoPoint = useCallback(() => {
    setStageZoneDraft((prev) => prev.slice(0, -1))
  }, [])

  const handleStageZoneFinish = useCallback(() => {
    if (stageZoneDraft.length < 3) return
    const targetIds = orchardTreePoints
      .filter((point) => pointInPolygon([point.lon, point.lat], stageZoneDraft))
      .map((point) => point.tree_id)

    setPhenologyZones((prev) => ([
      ...prev,
      {
        id: `stage-zone-${Date.now()}`,
        stage: stageZoneStage,
        coordinates: stageZoneDraft,
        tree_count: targetIds.length,
      },
    ]))
    setTreeStageOverrides((prev) => {
      const next = { ...prev }
      for (const id of targetIds) next[id] = stageZoneStage
      return next
    })
    setStageZoneDraft([])
    setStageZoneDrawing(false)
    setZoneHistory((prev) => [...prev, { type: 'stage' }])
  }, [orchardTreePoints, stageZoneDraft, stageZoneStage])

  const handleStageZoneUndoLast = useCallback(() => {
    const nextZones = phenologyZones.slice(0, -1)
    setPhenologyZones(nextZones)
    setTreeStageOverrides(stageOverridesFromZones(nextZones, orchardTreePoints))
    setStageZoneDraft([])
    setStageZoneDrawing(false)
  }, [orchardTreePoints, phenologyZones])

  // ── Status zone handlers (bulk status change) ─────────────────────────
  const handleStatusZoneStart = useCallback(() => {
    // Cancel any active stage zone drawing (mutual exclusivity)
    setStageZoneDraft([])
    setStageZoneDrawing(false)
    setCecidZoneDraft([])
    setCecidZoneEditingId(null)
    setCecidZoneDrawing(false)
    setStatusZoneDraft([])
    setStatusZoneDrawing(true)
  }, [])

  const handleStatusZoneCancel = useCallback(() => {
    setStatusZoneDraft([])
    setStatusZoneDrawing(false)
  }, [])

  const handleStatusZoneMapClick = useCallback((coordinate) => {
    setStatusZoneDraft((prev) => [...prev, coordinate])
  }, [])

  const handleStatusZoneUndoPoint = useCallback(() => {
    setStatusZoneDraft((prev) => prev.slice(0, -1))
  }, [])

  const handleStatusZoneFinish = useCallback(() => {
    if (statusZoneDraft.length < 3) return
    const targetIds = orchardTreePoints
      .filter((point) => pointInPolygon([point.lon, point.lat], statusZoneDraft))
      .map((point) => point.tree_id)

    setStatusZones((prev) => ([
      ...prev,
      {
        id: `status-zone-${Date.now()}`,
        status: statusZoneStatus,
        coordinates: statusZoneDraft,
        tree_count: targetIds.length,
      },
    ]))
    setTreeOverrides((prev) => {
      const next = { ...prev }
      for (const id of targetIds) next[id] = statusZoneStatus
      return next
    })
    setStatusZoneDraft([])
    setStatusZoneDrawing(false)
    setZoneHistory((prev) => [...prev, { type: 'status' }])
  }, [orchardTreePoints, statusZoneDraft, statusZoneStatus])

  const handleStatusZoneUndoLast = useCallback(() => {
    const removed = statusZones[statusZones.length - 1]
    const nextZones = statusZones.slice(0, -1)
    setStatusZones(nextZones)
    // Remove the tree overrides that were set by the removed zone
    if (removed) {
      const removedIds = new Set(
        orchardTreePoints
          .filter((point) => pointInPolygon([point.lon, point.lat], removed.coordinates))
          .map((point) => point.tree_id),
      )
      setTreeOverrides((prev) => {
        const next = { ...prev }
        for (const id of removedIds) delete next[id]
        // Re-apply remaining status zones in order
        for (const zone of nextZones) {
          const ids = orchardTreePoints
            .filter((point) => pointInPolygon([point.lon, point.lat], zone.coordinates))
            .map((point) => point.tree_id)
          for (const zoneId of ids) next[zoneId] = zone.status
        }
        return next
      })
    }
    setStatusZoneDraft([])
    setStatusZoneDrawing(false)
  }, [orchardTreePoints, statusZones])

  const handleStatusZoneClear = useCallback(() => {
    setStatusZones([])
    setTreeOverrides({})
    setStatusZoneDraft([])
    setStatusZoneDrawing(false)
  }, [])

  const handleCecidZoneStart = useCallback(() => {
    setStageZoneDraft([])
    setStageZoneDrawing(false)
    setStatusZoneDraft([])
    setStatusZoneDrawing(false)
    setCecidZoneDraft([])
    setCecidZoneEditingId(null)
    setCecidZoneDrawing(true)
  }, [])

  const handleCecidZoneCancel = useCallback(() => {
    setCecidZoneDraft([])
    setCecidZoneEditingId(null)
    setCecidZoneDrawing(false)
  }, [])

  const handleCecidZoneMapClick = useCallback((coordinate) => {
    setCecidZoneDraft((prev) => [...prev, coordinate])
  }, [])

  const handleCecidZoneUndoPoint = useCallback(() => {
    setCecidZoneDraft((prev) => prev.slice(0, -1))
  }, [])

  const handleCecidZoneFinish = useCallback(() => {
    if (cecidZoneDraft.length < 3) return
    const treeCount = orchardTreePoints.filter((point) => (
      pointInPolygon([point.lon, point.lat], cecidZoneDraft)
    )).length
    const newZone = {
      id: cecidZoneEditingId || `weed-zone-${Date.now()}`,
      label: cecidZoneLabel.trim() || `Weed habitat ${cecidWeedZones.length + 1}`,
      density: cecidZoneDensity,
      coordinates: cecidZoneDraft,
      tree_count: treeCount,
    }
    const nextZones = cecidZoneEditingId
      ? cecidWeedZones.map((zone) => (zone.id === cecidZoneEditingId ? newZone : zone))
      : [...cecidWeedZones, newZone]
    persistCecidWeedZones(nextZones)
    setCecidZoneDraft([])
    setCecidZoneDrawing(false)
    setCecidZoneEditingId(null)
    if (!cecidZoneEditingId) {
      setZoneHistory((prev) => [...prev, { type: 'cecid', id: newZone.id }])
    }
  }, [
    cecidWeedZones,
    cecidZoneDensity,
    cecidZoneDraft,
    cecidZoneEditingId,
    cecidZoneLabel,
    orchardTreePoints,
    persistCecidWeedZones,
  ])

  const handleCecidZoneRedraw = useCallback((zoneId) => {
    const zone = cecidWeedZones.find((candidate) => candidate.id === zoneId)
    if (!zone) return
    setStageZoneDraft([])
    setStageZoneDrawing(false)
    setStatusZoneDraft([])
    setStatusZoneDrawing(false)
    setCecidZoneLabel(zone.label)
    setCecidZoneDensity(zone.density)
    setCecidZoneDraft([])
    setCecidZoneEditingId(zone.id)
    setCecidZoneDrawing(true)
  }, [cecidWeedZones])

  const handleCecidZoneUpdate = useCallback((zoneId, patch) => {
    const nextZones = cecidWeedZones.map((zone) => (
      zone.id === zoneId ? { ...zone, ...patch } : zone
    ))
    persistCecidWeedZones(nextZones)
  }, [cecidWeedZones, persistCecidWeedZones])

  const handleCecidZoneDelete = useCallback((zoneId) => {
    const nextZones = cecidWeedZones.filter((zone) => zone.id !== zoneId)
    persistCecidWeedZones(nextZones)
    if (cecidZoneEditingId === zoneId) {
      setCecidZoneDraft([])
      setCecidZoneDrawing(false)
      setCecidZoneEditingId(null)
    }
    setZoneHistory((current) => current.filter((entry) => (
      entry.type !== 'cecid' || entry.id !== zoneId
    )))
  }, [cecidWeedZones, cecidZoneEditingId, persistCecidWeedZones])

  const handleCecidZoneClear = useCallback(() => {
    if (!cecidWeedZones.length) return
    if (!window.confirm('Clear all weed habitat zones from this orchard?')) return
    persistCecidWeedZones([])
    setCecidZoneDraft([])
    setCecidZoneDrawing(false)
    setCecidZoneEditingId(null)
    setZoneHistory((current) => current.filter((entry) => entry.type !== 'cecid'))
  }, [cecidWeedZones.length, persistCecidWeedZones])

  const handleStageZoneClear = useCallback(() => {
    setPhenologyZones([])
    setTreeStageOverrides({})
    setStageZoneDraft([])
    setStageZoneDrawing(false)
  }, [])

  // ── Unified zone undo / clear ─────────────────────────────────────────
  const handleZoneUndoLast = useCallback(() => {
    if (!zoneHistory.length) return
    const last = zoneHistory[zoneHistory.length - 1]
    setZoneHistory((prev) => prev.slice(0, -1))
    if (last.type === 'stage') {
      const nextZones = phenologyZones.slice(0, -1)
      setPhenologyZones(nextZones)
      setTreeStageOverrides(stageOverridesFromZones(nextZones, orchardTreePoints))
      setStageZoneDraft([])
      setStageZoneDrawing(false)
    } else if (last.type === 'status') {
      const removed = statusZones[statusZones.length - 1]
      const nextZones = statusZones.slice(0, -1)
      setStatusZones(nextZones)
      if (removed) {
        const removedIds = new Set(
          orchardTreePoints
            .filter((point) => pointInPolygon([point.lon, point.lat], removed.coordinates))
            .map((point) => point.tree_id),
        )
        setTreeOverrides((prev) => {
          const next = { ...prev }
          for (const id of removedIds) delete next[id]
          for (const zone of nextZones) {
            const ids = orchardTreePoints
              .filter((point) => pointInPolygon([point.lon, point.lat], zone.coordinates))
              .map((point) => point.tree_id)
            for (const zoneId of ids) next[zoneId] = zone.status
          }
          return next
        })
      }
      setStatusZoneDraft([])
      setStatusZoneDrawing(false)
    } else {
      const nextZones = last.id
        ? cecidWeedZones.filter((zone) => zone.id !== last.id)
        : cecidWeedZones.slice(0, -1)
      persistCecidWeedZones(nextZones)
      setCecidZoneDraft([])
      setCecidZoneEditingId(null)
      setCecidZoneDrawing(false)
    }
  }, [
    cecidWeedZones,
    orchardTreePoints,
    persistCecidWeedZones,
    phenologyZones,
    statusZones,
    zoneHistory,
  ])

  const handleZoneClearAll = useCallback(() => {
    if (cecidWeedZones.length && !window.confirm('Clear all zones, including saved weed habitats, from this orchard?')) return
    setPhenologyZones([])
    setTreeStageOverrides({})
    setStageZoneDraft([])
    setStageZoneDrawing(false)
    setStatusZones([])
    setTreeOverrides({})
    setStatusZoneDraft([])
    setStatusZoneDrawing(false)
    if (cecidWeedZones.length) persistCecidWeedZones([])
    setCecidZoneDraft([])
    setCecidZoneEditingId(null)
    setCecidZoneDrawing(false)
    setZoneHistory([])
  }, [cecidWeedZones.length, persistCecidWeedZones])

  return (
    <div className="app-shell">
      <Navbar
        alerts={activeOrchardAlerts}
        alertLoading={alertLoading}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        onAlertRefresh={fetchAlerts}
        onApplySuggested={handleSuggestedSimulation}
        onControlsOpen={() => setSidebarMobileOpen(true)}
      />

      <div className="viewport-layout">
        {/* ── Main content area (map + tabs) ── */}
        <main className="fullscreen-map-area">
          <div className="ops-pages-shell">
            {/* Tab panels */}
            <div className="ops-tab-body" id="ops-tab-body">
              <div
                id="ops-panel-live-map"
                className="ops-panel"
                style={{ display: activeTab === 'live-map' ? 'block' : 'none' }}
              >
                <LiveMapTab
                  geojson={mapGeojson}
                  baseGeojson={orchardGeojson}
                  alerts={mapAlerts}
                  treeOverrides={treeOverrides}
                  stageOverrides={treeStageOverrides}
                  stageZones={phenologyZones}
                  stageZoneDrawing={stageZoneDrawing}
                  stageZoneStage={stageZoneStage}
                  stageZoneDraft={stageZoneDraft}
                  stageOptions={PHENOLOGY_STAGE_OPTIONS}
                  onStageZoneStageChange={setStageZoneStage}
                  onStageZoneStart={handleStageZoneStart}
                  onStageZoneCancel={handleStageZoneCancel}
                  onStageZoneFinish={handleStageZoneFinish}
                  onStageZoneUndoPoint={handleStageZoneUndoPoint}
                  onStageZoneMapClick={handleStageZoneMapClick}
                  statusZones={statusZones}
                  statusZoneDrawing={statusZoneDrawing}
                  statusZoneStatus={statusZoneStatus}
                  statusZoneDraft={statusZoneDraft}
                  statusOptions={STATUS_ZONE_OPTIONS}
                  onStatusZoneStatusChange={setStatusZoneStatus}
                  onStatusZoneStart={handleStatusZoneStart}
                  onStatusZoneCancel={handleStatusZoneCancel}
                  onStatusZoneFinish={handleStatusZoneFinish}
                  onStatusZoneUndoPoint={handleStatusZoneUndoPoint}
                  onStatusZoneMapClick={handleStatusZoneMapClick}
                  cecidWeedZones={cecidWeedZones}
                  legacyCecidEmergenceZones={legacyCecidEmergenceZones}
                  cecidZoneDrawing={cecidZoneDrawing}
                  cecidZoneDensity={cecidZoneDensity}
                  cecidZoneLabel={cecidZoneLabel}
                  cecidZoneDraft={cecidZoneDraft}
                  cecidZoneSaveState={cecidZoneSaveState}
                  cecidZoneSaveError={cecidZoneSaveError}
                  onCecidZoneDensityChange={setCecidZoneDensity}
                  onCecidZoneLabelChange={setCecidZoneLabel}
                  onCecidZoneStart={handleCecidZoneStart}
                  onCecidZoneCancel={handleCecidZoneCancel}
                  onCecidZoneFinish={handleCecidZoneFinish}
                  onCecidZoneUndoPoint={handleCecidZoneUndoPoint}
                  onCecidZoneMapClick={handleCecidZoneMapClick}
                  onCecidZoneUpdate={handleCecidZoneUpdate}
                  onCecidZoneRedraw={handleCecidZoneRedraw}
                  onCecidZoneDelete={handleCecidZoneDelete}
                  onCecidZoneClear={handleCecidZoneClear}
                  onCecidZoneRetry={retryCecidWeedZoneSave}
                  selectedPestType={selectedPestType}
                  zoneHistory={zoneHistory}
                  onZoneUndoLast={handleZoneUndoLast}
                  onZoneClearAll={handleZoneClearAll}
                  orchardName={orchardName}
                  orthophotoOverlay={orchardOrthophoto}
                  viewportKey={`${selectedOrchardId}:${mapRefreshKey}`}
                  fitToOrthophoto
                  currentFrame={currentFrame}
                  onTreeClick={handleTreeClick}
                />
              </div>

              <div
                id="ops-panel-overview"
                className="ops-panel ops-panel-scroll"
                style={{ display: activeTab === 'overview' ? 'block' : 'none' }}
              >
                <OverviewTab
                  monitoringData={monitoringData}
                  simData={simData}
                  currentFrame={currentFrame}
                  totalTrees={orchardGeojson?.features?.length ?? 0}
                />
              </div>

              <div
                id="ops-panel-impact"
                className="ops-panel ops-panel-scroll"
                style={{ display: activeTab === 'crop-impact' ? 'block' : 'none' }}
              >
                <CropImpactTab monitoringData={monitoringData} simData={simData} />
              </div>

              <div
                id="ops-panel-surveillance"
                className="ops-panel ops-panel-scroll"
                style={{ display: activeTab === 'spread-weather' ? 'block' : 'none' }}
              >
                <SurveillanceTab monitoringData={monitoringData} simData={simData} weather={weather} />
              </div>

              <div
                id="ops-panel-history"
                className="ops-panel ops-panel-scroll"
                style={{ display: activeTab === 'history' ? 'block' : 'none' }}
              >
                <SimulationHistoryTab
                  orchards={orchards}
                  refreshKey={historyRefreshKey}
                  onLoadRun={handleHistoricalSimulationLoad}
                  onUseTemplate={handleHistoricalTemplateLoad}
                />
              </div>

            </div>
          </div>
        </main>

        {/* ── Right sidebar ── */}
        <Sidebar
          orchards={orchards}
          selectedOrchardId={selectedOrchardId}
          onOrchardSelect={handleOrchardSelect}
          onOrchardRefresh={handleOrchardRefresh}
          onOrchardUpload={handleOrchardUpload}
          orchardLoading={orchardLoading}
          defaultTreeCount={fallbackGeojson?.features?.length ?? 0}
          weather={weather}
          manualWeather={manualWeather}
          weatherOverrideActive={weatherOverrideActive}
          weatherTimeline={weatherTimeline}
          onManualWeatherChange={(w) => {
            setManualWeather(w)
            setWeatherTimeline((current) => ({ ...current, enabled: false }))
            setWeatherOverrideActive(true)
          }}
          onWeatherOverrideToggle={setWeatherOverrideActive}
          onWeatherTimelineChange={setWeatherTimeline}
          onWeatherRetry={() => fetchWeather(true)}
          orchardCoordinates={orchardWeatherCoordinates}
          orchardGeojson={orchardGeojson}
          treeOverrides={treeOverrides}
          treeStageOverrides={treeStageOverrides}
          phenologyZones={phenologyZones}
          cecidWeedZones={cecidWeedZones}
          legacyCecidEmergenceZones={legacyCecidEmergenceZones}
          onPestTypeChange={setSelectedPestType}
          onClearTreeStageOverrides={handleStageZoneClear}
          onSimulationComplete={handleSimulationComplete}
          simulationTemplate={simulationTemplate}
          playbackFrames={playbackFrames}
          currentFrameIdx={currentFrameIdx}
          onFrameSeek={setCurrentFrameIdx}
          decisionMetrics={decisionMetrics}
          suggestedSimParams={suggestedSimParams}
          onClearSuggestedSimParams={() => setSuggestedSimParams(null)}
          activeWorkflow={sidebarWorkflow}
          onWorkflowChange={setSidebarWorkflow}
          collapsed={sidebarCollapsed}
          onCollapsedChange={setSidebarCollapsed}
          mobileOpen={sidebarMobileOpen}
          onMobileOpenChange={setSidebarMobileOpen}
        />
      </div>

      {/* ── Tree Management Modal ── */}
      {selectedTree && (
        <div
          className="modal fade show d-block"
          tabIndex="-1"
          style={{ background: 'rgba(0,0,0,.5)' }}
          onClick={(e) => { if (e.target === e.currentTarget) setSelectedTree(null) }}
        >
          <div className="modal-dialog modal-dialog-centered">
            <div className="modal-content">
              <div className="modal-header bg-light border-bottom">
                <h5 className="modal-title">
                  <i className="bi bi-tree-fill me-2" style={{ color: '#22c55e' }} />
                  Tree Management
                </h5>
                <button type="button" className="btn-close" onClick={() => setSelectedTree(null)} />
              </div>
              <div className="modal-body px-4 py-3">
                <div className="mb-4">
                  <p className="mb-1"><strong>Tree #{selectedTree.tree_id}</strong></p>
                  <p className="text-muted small mb-1">
                    Current status: {(selectedTree.status ?? 'healthy').replace(/_/g, ' ')}
                  </p>
                  {selectedTree.risk != null && (
                    <p className="text-muted small mb-0">
                      Risk: {(selectedTree.risk * 100).toFixed(0)}%
                    </p>
                  )}
                </div>
                <hr className="my-2" />
                <div className="d-flex align-items-center mb-2">
                  <i className="bi bi-pencil-square me-2 text-primary" />
                  <strong className="text-primary">Override Status</strong>
                </div>
                <TreeStatusSelect
                  defaultValue={selectedTree.status ?? 'healthy'}
                  onApply={(status) => applyTreeStatus(selectedTree.tree_id, status)}
                  onCancel={() => setSelectedTree(null)}
                />
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function TreeStatusSelect({ defaultValue, onApply, onCancel }) {
  const [value, setValue] = useState(defaultValue)

  const OPTIONS = [
    { label: 'Healthy', value: 'healthy' },
    { label: 'Infected', value: 'infected' },
    { label: 'Bagged (reduced risk)', value: 'bagged' },
    { label: 'Dead (removed)', value: 'dead' },
    { label: 'History Infected', value: 'history_infected' },
    { label: 'Suspect (monitoring)', value: 'suspect' },
  ]

  return (
    <>
      <select
        className="form-select mb-3 border-primary"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        style={{ fontSize: '.95rem' }}
      >
        {OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      <div className="card bg-light border-0 mb-3">
        <div className="card-body py-2 px-3">
          <div className="d-flex align-items-center">
            <i className="bi bi-info-circle-fill me-2 text-info" />
            <span className="small">Status changes take effect on the next simulation run.</span>
          </div>
          <div className="d-flex align-items-center mt-2">
            <i className="bi bi-shield-check me-2 text-success" />
            <span className="small">
              <strong>Bagged</strong> trees have reduced infection risk;{' '}
              <strong>Dead</strong> trees are immune to pest spread.
            </span>
          </div>
        </div>
      </div>
      <div className="modal-footer bg-light border-top p-2 d-flex gap-2">
        <button type="button" className="btn btn-outline-secondary px-4" onClick={onCancel}>
          <i className="bi bi-x-lg me-1" />Cancel
        </button>
        <button type="button" className="btn btn-success px-4 ms-2" onClick={() => onApply(value)}>
          <i className="bi bi-check-lg me-1" />Apply Changes
        </button>
      </div>
    </>
  )
}
