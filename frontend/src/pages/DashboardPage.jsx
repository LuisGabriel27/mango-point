import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import Navbar from '../components/Navbar'
import Sidebar from '../components/Sidebar'
import LiveMapTab from '../components/tabs/LiveMapTab'
import OverviewTab from '../components/tabs/OverviewTab'
import CropImpactTab from '../components/tabs/CropImpactTab'
import SurveillanceTab from '../components/tabs/SurveillanceTab'
import SimulationHistoryTab from '../components/tabs/SimulationHistoryTab'
import SimulationReportModal from '../components/SimulationReportModal'
import api from '../api'
import { saveSimulationRunToHistory } from '../utils/simulationHistoryStore'
import { prepareAlertSimulationSuggestion } from '../utils/alertSimulation'
import { summarizeCecidResult } from '../utils/cecidResultSummary'
import { calculateSimulationEconomicImpact } from '../utils/economicImpact'
import { buildGuidedBlocks, createDefaultWeatherTimeline } from '../utils/weatherSchedule'
import {
  normalizeCecidWeedZones,
  saveCecidWeedZones,
} from '../utils/cecidWeedZones'
import {
  normalizeManagementZones,
  saveManagementZones,
} from '../utils/managementZones'
import {
  normalizeStageZones,
  normalizeStatusZones,
  stageZonePayload,
  statusZonePayload,
} from '../utils/orchardTreeZones'
import {
  overlappingManagementZones,
  treeIdsInPolygon,
} from '../utils/zoneSelection'
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
  stage_zones: [],
  status_zones: [],
  management_zones: [],
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

function parseMaybeJson(value, fallback) {
  if (value == null) return fallback
  if (typeof value !== 'string') return value
  try {
    return JSON.parse(value)
  } catch (_) {
    return fallback
  }
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

    for (const treeId of treeIdsInPolygon(treePoints, coordinates)) overrides[treeId] = zone.stage
  }

  return overrides
}

function statusOverridesFromZones(zones, treePoints) {
  const overrides = {}
  for (const zone of zones || []) {
    const coordinates = Array.isArray(zone?.coordinates) ? zone.coordinates : []
    if (coordinates.length < 3 || !zone?.status) continue
    for (const treeId of treeIdsInPolygon(treePoints, coordinates)) overrides[treeId] = zone.status
  }
  return overrides
}

function persistentZoneReapplyUpdates(kind, affectedIds, remainingZones, treePoints, resetValue) {
  if (!affectedIds.length) return []
  const affected = new Set(affectedIds.map(String))
  const updates = [{ treeIds: [...affected], patch: { [kind]: resetValue } }]
  for (const zone of remainingZones) {
    if (zone.scope !== 'orchard') continue
    const overlappingIds = treeIdsInPolygon(treePoints, zone.coordinates)
      .filter((treeId) => affected.has(String(treeId)))
    if (overlappingIds.length) {
      updates.push({ treeIds: overlappingIds, patch: { [kind]: zone[kind] } })
    }
  }
  return updates
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
  const [reportRequest, setReportRequest] = useState(null)
  const [treeOverrides, setTreeOverrides] = useState({})
  const [treeStageOverrides, setTreeStageOverrides] = useState({})
  const [phenologyZones, setPhenologyZones] = useState([])
  const [stageZoneDrawing, setStageZoneDrawing] = useState(false)
  const [stageZoneStage, setStageZoneStage] = useState('mature')
  const [stageZoneDraft, setStageZoneDraft] = useState([])
  const [playbackFrames, setPlaybackFrames] = useState([])
  const [currentFrameIdx, setCurrentFrameIdx] = useState(0)
  const [cecidMapMode, setCecidMapMode] = useState('representative')
  const [mapRefreshKey, setMapRefreshKey] = useState(0)
  const [simulationTemplate, setSimulationTemplate] = useState(null)
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0)
  const [selectedPestType, setSelectedPestType] = useState('fruitfly')

  // Status zone drawing (bulk status change)
  const [statusZoneDrawing, setStatusZoneDrawing] = useState(false)
  const [statusZoneStatus, setStatusZoneStatus] = useState('infected')
  const [statusZoneDraft, setStatusZoneDraft] = useState([])
  const [statusZones, setStatusZones] = useState([])
  const [treeEditScope, setTreeEditScope] = useState('scenario')
  const [treeEditSaveState, setTreeEditSaveState] = useState('idle')
  const [treeEditSaveError, setTreeEditSaveError] = useState('')
  const treeZoneOrchardIdRef = useRef(null)
  const treeZoneSaveVersionRef = useRef({ stage: 0, status: 0 })
  const treeZoneSaveQueueRef = useRef(Promise.resolve())

  // Persistent named areas used by field teams and future zone reports.
  const [managementZones, setManagementZones] = useState([])
  const [managementZoneDrawing, setManagementZoneDrawing] = useState(false)
  const [managementZoneLabel, setManagementZoneLabel] = useState('Zone 1')
  const [managementZoneDraft, setManagementZoneDraft] = useState([])
  const [managementZoneEditingId, setManagementZoneEditingId] = useState(null)
  const [managementZoneSaveState, setManagementZoneSaveState] = useState('idle')
  const [managementZoneSaveError, setManagementZoneSaveError] = useState('')
  const managementZoneSaveVersionRef = useRef(0)

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
  const [observationPrefill, setObservationPrefill] = useState({
    treeIds: [], forecastRisk: null, forecastLeadHours: null, lon: null, lat: null,
  })

  // Fallback GeoJSON from static file (mirrors Python app's DEFAULT_ORCHARD)
  const [fallbackGeojson, setFallbackGeojson] = useState(fallbackTreeGeojson)
  useEffect(() => {
    selectedOrchardIdRef.current = selectedOrchardId
  }, [selectedOrchardId])

  useEffect(() => {
    setObservationPrefill({
      treeIds: [], forecastRisk: null, forecastLeadHours: null, lon: null, lat: null,
    })
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
  const selectedOrchardManagementZonesKey = useMemo(
    () => JSON.stringify(selectedOrchardRecord?.management_zones ?? []),
    [selectedOrchardRecord?.management_zones],
  )
  const selectedOrchardStageZonesKey = useMemo(
    () => JSON.stringify(selectedOrchardRecord?.stage_zones ?? []),
    [selectedOrchardRecord?.stage_zones],
  )
  const selectedOrchardStatusZonesKey = useMemo(
    () => JSON.stringify(selectedOrchardRecord?.status_zones ?? []),
    [selectedOrchardRecord?.status_zones],
  )

  useEffect(() => {
    const orchardChanged = treeZoneOrchardIdRef.current !== selectedOrchardId
    const savedStageZones = normalizeStageZones(selectedOrchardRecord?.stage_zones, 'orchard')
    const savedStatusZones = normalizeStatusZones(selectedOrchardRecord?.status_zones, 'orchard')
    setPhenologyZones((current) => [
      ...(orchardChanged ? [] : current.filter((zone) => zone.scope !== 'orchard')),
      ...savedStageZones,
    ])
    setStatusZones((current) => [
      ...(orchardChanged ? [] : current.filter((zone) => zone.scope !== 'orchard')),
      ...savedStatusZones,
    ])
    if (orchardChanged) {
      setTreeStageOverrides({})
      setTreeOverrides({})
      setZoneHistory([])
    }
    treeZoneOrchardIdRef.current = selectedOrchardId
    setTreeEditSaveState('idle')
    setTreeEditSaveError('')
  }, [
    selectedOrchardId,
    selectedOrchardStageZonesKey,
    selectedOrchardStatusZonesKey,
  ])

  useEffect(() => {
    setCecidWeedZones(normalizeCecidWeedZones(selectedOrchardRecord?.cecid_weed_zones))
    setLegacyCecidEmergenceZones([])
    setCecidZoneEditingId(null)
    setCecidZoneSaveState('idle')
    setCecidZoneSaveError('')
  }, [selectedOrchardId, selectedOrchardWeedZonesKey])

  useEffect(() => {
    setManagementZones(normalizeManagementZones(selectedOrchardRecord?.management_zones))
    setManagementZoneEditingId(null)
    setManagementZoneSaveState('idle')
    setManagementZoneSaveError('')
  }, [selectedOrchardId, selectedOrchardManagementZonesKey])

  useEffect(() => {
    if (treeEditSaveState !== 'saved') return undefined
    const timeoutId = window.setTimeout(() => {
      setTreeEditSaveState('idle')
      setTreeEditSaveError('')
    }, 2200)
    return () => window.clearTimeout(timeoutId)
  }, [treeEditSaveState])

  const stageZoneSelectedCount = useMemo(
    () => treeIdsInPolygon(orchardTreePoints, stageZoneDraft).length,
    [orchardTreePoints, stageZoneDraft],
  )
  const statusZoneSelectedCount = useMemo(
    () => treeIdsInPolygon(orchardTreePoints, statusZoneDraft).length,
    [orchardTreePoints, statusZoneDraft],
  )
  const managementZoneSelectedCount = useMemo(
    () => treeIdsInPolygon(orchardTreePoints, managementZoneDraft).length,
    [managementZoneDraft, orchardTreePoints],
  )
  const cecidZoneSelectedCount = useMemo(
    () => treeIdsInPolygon(orchardTreePoints, cecidZoneDraft).length,
    [cecidZoneDraft, orchardTreePoints],
  )

  // Cecid defaults to a repeated-run likelihood map. Playback remains the
  // exact representative realization and never changes the model result.
  const currentFrame = playbackFrames.length > 0 ? (playbackFrames[currentFrameIdx] ?? null) : null
  const cecidEnsembleRuns = Number(
    simData?.metadata?.cecid_uncertainty_summary?.runs ?? 0,
  )
  const cecidTreeLikelihoodAvailable = Boolean(
    simData?.risk_geojson?.features?.some((feature) => (
      Number(feature?.properties?.ensemble_runs) > 1
    )),
  )
  const cecidLikelihoodAvailable = simData?.pest_type === 'cecid'
    && cecidEnsembleRuns > 1
    && cecidTreeLikelihoodAvailable
  const mapGeojson = cecidLikelihoodAvailable && cecidMapMode === 'likelihood'
    ? simData?.risk_geojson ?? null
    : currentFrame?.risk_geojson ?? simData?.risk_geojson ?? null
  const displayedFrame = cecidLikelihoodAvailable && cecidMapMode === 'likelihood'
    ? null
    : currentFrame

  const handleOpenSimulationReport = useCallback((run, includeDisplayed = false) => {
    if (!run) return
    const params = parseMaybeJson(run.request_payload ?? run.input_parameters, {})
    const orchardId = run.orchard_id ?? params.orchard_id ?? (includeDisplayed ? selectedOrchardId : DEFAULT_ORCHARD_ID)
    const record = orchards.find((orchard) => orchard.orchard_id === orchardId)
    setReportRequest({
      run,
      orchard: {
        ...record,
        orchard_id: orchardId,
        name: record?.name || (orchardId === DEFAULT_ORCHARD_ID ? DEFAULT_ORCHARD_LABEL : orchardId),
        geojson: record?.geojson ?? (orchardId === DEFAULT_ORCHARD_ID ? fallbackGeojson : null),
      },
      displayed: includeDisplayed ? { geojson: mapGeojson, frame: displayedFrame, mode: cecidMapMode } : null,
    })
  }, [orchards, selectedOrchardId, fallbackGeojson, mapGeojson, displayedFrame, cecidMapMode])
  const handleCloseSimulationReport = useCallback(() => setReportRequest(null), [])

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
    const cecid = simData.pest_type === 'cecid'
      ? summarizeCecidResult(simData)
      : null
    const economic = calculateSimulationEconomicImpact(simData)
    const pesticideReduction = Math.max(0, 1 - (z3 > 0.02 ? z3 : 0))

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
      economic: economic ? { ...economic, pesticide_reduction: pesticideReduction } : null,
      action_plan: actions,
      summary_message: summary,
      cecid,
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

  const persistManagementZones = useCallback(async (nextZones) => {
    const orchardId = selectedOrchardIdRef.current || DEFAULT_ORCHARD_ID
    const normalized = normalizeManagementZones(nextZones)
    const saveVersion = managementZoneSaveVersionRef.current + 1
    managementZoneSaveVersionRef.current = saveVersion
    setManagementZones(normalized)
    setManagementZoneSaveState('saving')
    setManagementZoneSaveError('')

    const outcome = await saveManagementZones(orchardId, normalized, api.updateOrchard)
    if (
      managementZoneSaveVersionRef.current !== saveVersion
      || selectedOrchardIdRef.current !== orchardId
    ) return
    if (!outcome.ok) {
      setManagementZoneSaveState('error')
      setManagementZoneSaveError(outcome.message)
      return
    }
    const savedRecord = outcome.response.data
    setManagementZones(outcome.zones)
    setOrchards((current) => current.map((record) => (
      record.orchard_id === orchardId ? { ...record, ...savedRecord } : record
    )))
    setManagementZoneSaveState('saved')
  }, [])

  const retryManagementZoneSave = useCallback(() => {
    persistManagementZones(managementZones)
  }, [managementZones, persistManagementZones])

  const persistOrchardTreeZones = useCallback((kind, nextZones, treeUpdates = []) => {
    const orchardId = selectedOrchardIdRef.current || DEFAULT_ORCHARD_ID
    const saveVersion = treeZoneSaveVersionRef.current[kind] + 1
    treeZoneSaveVersionRef.current[kind] = saveVersion
    const field = kind === 'stage' ? 'stage_zones' : 'status_zones'
    const payload = kind === 'stage' ? stageZonePayload(nextZones) : statusZonePayload(nextZones)
    setTreeEditSaveState('saving')
    setTreeEditSaveError('')
    const save = async () => {
      try {
        let response = await api.updateOrchard(orchardId, { [field]: payload })
        let savedRecord = response.data
        for (const update of treeUpdates) {
          if (!update.treeIds?.length) continue
          response = await api.updateOrchardTrees(orchardId, {
            tree_ids: update.treeIds,
            ...update.patch,
          })
          savedRecord = response.data.orchard
        }
        if (
          treeZoneSaveVersionRef.current[kind] !== saveVersion
          || selectedOrchardIdRef.current !== orchardId
        ) return false
        setOrchards((current) => current.map((record) => (
          record.orchard_id === orchardId
            ? { ...record, geojson: savedRecord.geojson, [field]: savedRecord[field] ?? payload }
            : record
        )))
        setTreeEditSaveState('saved')
        return true
      } catch (error) {
        if (
          treeZoneSaveVersionRef.current[kind] !== saveVersion
          || selectedOrchardIdRef.current !== orchardId
        ) return false
        setTreeEditSaveState('error')
        setTreeEditSaveError(
          error?.response?.data?.detail || error?.message || 'Could not save orchard zones.',
        )
        return false
      }
    }
    const pending = treeZoneSaveQueueRef.current.catch(() => false).then(save)
    treeZoneSaveQueueRef.current = pending
    return pending
  }, [])

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
    setManagementZones(normalizeManagementZones(uploaded.management_zones))
    setManagementZoneDrawing(false)
    setManagementZoneDraft([])
    setManagementZoneEditingId(null)
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
    setManagementZones([])
    setManagementZoneDrawing(false)
    setManagementZoneDraft([])
    setManagementZoneEditingId(null)
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

  const handleOrchardStageChange = useCallback(async (stage) => {
    const orchardId = selectedOrchardIdRef.current || DEFAULT_ORCHARD_ID
    const response = await api.updateOrchard(orchardId, { orchard_stage: stage })
    const saved = response.data
    setOrchards((current) => current.map((orchard) => (
      String(orchard.orchard_id) === String(orchardId)
        ? { ...orchard, ...saved }
        : orchard
    )))

    try {
      await api.checkWeatherForecast({
        orchard_id: orchardId,
        lat: saved?.centroid_lat ?? null,
        lon: saved?.centroid_lon ?? null,
        orchard_stage: saved?.orchard_stage ?? stage,
        monitored_pest_types: saved?.monitored_pest_types ?? null,
        hours: 48,
      })
    } catch (_) {
      // The saved stage remains valid; the hourly backend monitor will retry.
    }
    fetchAlerts()
    return saved
  }, [fetchAlerts])

  const handleOrchardRefresh = useCallback(async () => {
    // Refresh server data without treating the action as an orchard reset.
    // Scenario-only stage/status selections and the current result stay put;
    // persistent management/weed zones are reconciled from the API response.
    await fetchOrchards(selectedOrchardIdRef.current)
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
    const prepared = prepareAlertSimulationSuggestion(params)
    if (
      prepared.orchardId
      && prepared.orchardId !== selectedOrchardIdRef.current
      && orchards.some((orchard) => String(orchard.orchard_id) === prepared.orchardId)
    ) {
      handleOrchardSelect(prepared.orchardId)
    }
    if (prepared.useLiveWeather) {
      setWeatherOverrideActive(false)
      fetchWeather(true)
    }
    // Copy the object so clicking the same alert can restore controls again.
    setSuggestedSimParams({ ...prepared.params })
    setSidebarWorkflow((current) => sidebarWorkflowForEvent('alert-prefill', current))
    setSidebarCollapsed(false)
    if (typeof window.matchMedia === 'function' && window.matchMedia('(max-width: 991.98px)').matches) {
      setSidebarMobileOpen(true)
    }
  }, [fetchWeather, handleOrchardSelect, orchards])

  // ── Auto-refresh intervals ────────────────────────────────────────────
  useEffect(() => {
    const id = setInterval(fetchWeather, 60_000)
    return () => clearInterval(id)
  }, [fetchWeather])


  // ── Simulation complete handler ───────────────────────────────────────
  const applySimulationResult = useCallback((data, options = {}) => {
    setSimData(data)
    if (data?.pest_type) setSelectedPestType(data.pest_type)
    const frames = Array.isArray(data.time_series) ? data.time_series : []
    setPlaybackFrames(frames)
    setCurrentFrameIdx(options.startAtLastFrame && frames.length ? frames.length - 1 : 0)
    const ensembleRuns = Number(data?.metadata?.cecid_uncertainty_summary?.runs ?? 0)
    setCecidMapMode(data?.pest_type === 'cecid' && ensembleRuns > 1
      ? 'likelihood'
      : 'representative')
    fetchAlerts()
    window.setTimeout(fetchAlerts, 1200)
    fetchMonitoring()
  }, [fetchAlerts, fetchMonitoring])

  const handleFrameSeek = useCallback((frameIndex) => {
    setCurrentFrameIdx(frameIndex)
    if (simData?.pest_type === 'cecid') setCecidMapMode('representative')
  }, [simData?.pest_type])

  const handleCecidMapModeChange = useCallback((mode) => {
    setCecidMapMode(mode)
    if (mode === 'representative' && playbackFrames.length) {
      setCurrentFrameIdx(playbackFrames.length - 1)
    }
  }, [playbackFrames.length])

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
    const savedStatusOverrides = parseMaybeJson(safeParams.tree_overrides, {})
    const savedZones = normalizeStageZones(
      dashboardState.phenology_zones ?? safeParams.phenology_zones,
    )
    const restoredStatusZones = normalizeStatusZones(dashboardState.status_zones)
    const restoredManagementZones = normalizeManagementZones(
      safeParams.management_zones ?? dashboardState.management_zones,
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
      setStatusZones(restoredStatusZones)
      setTreeOverrides(savedStatusOverrides)
      setStatusZoneDraft([])
      setStatusZoneDrawing(false)
      setStageZoneDraft([])
      setStageZoneDrawing(false)
      setManagementZones(restoredManagementZones)
      setManagementZoneDraft([])
      setManagementZoneEditingId(null)
      setManagementZoneDrawing(false)
      setCecidWeedZones(restoredCecidWeedZones)
      setLegacyCecidEmergenceZones(restoredLegacyCecidZones)
      setCecidZoneDraft([])
      setCecidZoneEditingId(null)
      setCecidZoneDrawing(false)
      setZoneHistory([
        ...restoredZones.map(() => ({ type: 'stage' })),
        ...restoredStatusZones.map(() => ({ type: 'status' })),
        ...restoredCecidWeedZones.map((zone) => ({ type: 'cecid', id: zone.id })),
      ])
      setMapRefreshKey((value) => value + 1)
    }

    if (options.defer) {
      setPhenologyZones([])
      setTreeStageOverrides({})
      setStatusZones([])
      setTreeOverrides({})
      setManagementZones([])
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

  const handleOpenTreeVerification = useCallback(() => {
    if (!selectedTree?.tree_id) return
    setObservationPrefill({
      treeIds: [String(selectedTree.tree_id)],
      forecastRisk: selectedTree.risk == null ? null : Number(selectedTree.risk),
      forecastLeadHours: Number.isFinite(Number(currentFrame?.hour ?? currentFrame?.timestep))
        ? Number(currentFrame?.hour ?? currentFrame?.timestep)
        : null,
      lon: Number.isFinite(Number(selectedTree.lon)) ? Number(selectedTree.lon) : null,
      lat: Number.isFinite(Number(selectedTree.lat)) ? Number(selectedTree.lat) : null,
    })
    setSidebarWorkflow((current) => sidebarWorkflowForEvent('tree-verification', current))
    setSidebarCollapsed(false)
    if (typeof window.matchMedia === 'function' && window.matchMedia('(max-width: 991.98px)').matches) {
      setSidebarMobileOpen(true)
    }
    setSelectedTree(null)
  }, [currentFrame, selectedTree])

  const handleStageZoneStart = useCallback(() => {
    setTreeEditSaveState('idle')
    setTreeEditSaveError('')
    // Cancel any active status zone drawing (mutual exclusivity)
    setStatusZoneDraft([])
    setStatusZoneDrawing(false)
    setCecidZoneDraft([])
    setCecidZoneEditingId(null)
    setCecidZoneDrawing(false)
    setManagementZoneDraft([])
    setManagementZoneEditingId(null)
    setManagementZoneDrawing(false)
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
    const targetIds = treeIdsInPolygon(orchardTreePoints, stageZoneDraft)
    const newZone = {
      id: `stage-zone-${Date.now()}`,
      stage: stageZoneStage,
      coordinates: stageZoneDraft,
      tree_count: targetIds.length,
      scope: treeEditScope,
    }
    const nextZones = [...phenologyZones, newZone]
    setPhenologyZones(nextZones)
    setTreeStageOverrides((prev) => {
      const next = { ...prev }
      for (const id of targetIds) next[id] = stageZoneStage
      return next
    })
    setStageZoneDraft([])
    setStageZoneDrawing(false)
    setZoneHistory((prev) => [...prev, { type: 'stage', id: newZone.id }])
    if (treeEditScope === 'orchard') {
      persistOrchardTreeZones('stage', nextZones, [{
        treeIds: targetIds,
        patch: { stage: stageZoneStage },
      }])
    }
  }, [
    orchardTreePoints,
    persistOrchardTreeZones,
    phenologyZones,
    stageZoneDraft,
    stageZoneStage,
    treeEditScope,
  ])

  // ── Status zone handlers (bulk status change) ─────────────────────────
  const handleStatusZoneStart = useCallback(() => {
    setTreeEditSaveState('idle')
    setTreeEditSaveError('')
    // Cancel any active stage zone drawing (mutual exclusivity)
    setStageZoneDraft([])
    setStageZoneDrawing(false)
    setCecidZoneDraft([])
    setCecidZoneEditingId(null)
    setCecidZoneDrawing(false)
    setManagementZoneDraft([])
    setManagementZoneEditingId(null)
    setManagementZoneDrawing(false)
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
    const targetIds = treeIdsInPolygon(orchardTreePoints, statusZoneDraft)
    const newZone = {
      id: `status-zone-${Date.now()}`,
      status: statusZoneStatus,
      coordinates: statusZoneDraft,
      tree_count: targetIds.length,
      scope: treeEditScope,
    }
    const nextZones = [...statusZones, newZone]
    setStatusZones(nextZones)
    setTreeOverrides((prev) => {
      const next = { ...prev }
      for (const id of targetIds) next[id] = statusZoneStatus
      return next
    })
    setStatusZoneDraft([])
    setStatusZoneDrawing(false)
    setZoneHistory((prev) => [...prev, { type: 'status', id: newZone.id }])
    if (treeEditScope === 'orchard') {
      persistOrchardTreeZones('status', nextZones, [{
        treeIds: targetIds,
        patch: { status: statusZoneStatus },
      }])
    }
  }, [
    orchardTreePoints,
    persistOrchardTreeZones,
    statusZones,
    statusZoneDraft,
    statusZoneStatus,
    treeEditScope,
  ])

  // ── Persistent management/reporting zone handlers ─────────────────────
  const handleStageZoneDelete = useCallback((zoneId) => {
    const removed = phenologyZones.find((zone) => zone.id === zoneId)
    if (!removed) return
    const nextZones = phenologyZones.filter((zone) => zone.id !== zoneId)
    const affectedIds = treeIdsInPolygon(orchardTreePoints, removed.coordinates)
    const nextOverrides = stageOverridesFromZones(nextZones, orchardTreePoints)
    const resetStage = selectedOrchardRecord?.orchard_stage || 'mature'
    if (removed.scope === 'orchard') {
      for (const treeId of affectedIds) {
        if (!(treeId in nextOverrides)) nextOverrides[treeId] = resetStage
      }
      persistOrchardTreeZones(
        'stage',
        nextZones,
        persistentZoneReapplyUpdates('stage', affectedIds, nextZones, orchardTreePoints, resetStage),
      )
    }
    setPhenologyZones(nextZones)
    setTreeStageOverrides(nextOverrides)
    setStageZoneDraft([])
    setStageZoneDrawing(false)
    setZoneHistory((current) => current.filter((entry) => (
      entry.type !== 'stage' || entry.id !== zoneId
    )))
  }, [
    orchardTreePoints,
    persistOrchardTreeZones,
    phenologyZones,
    selectedOrchardRecord?.orchard_stage,
  ])

  const handleStatusZoneDelete = useCallback((zoneId) => {
    const removed = statusZones.find((zone) => zone.id === zoneId)
    if (!removed) return
    const nextZones = statusZones.filter((zone) => zone.id !== zoneId)
    const affectedIds = treeIdsInPolygon(orchardTreePoints, removed.coordinates)
    const nextOverrides = statusOverridesFromZones(nextZones, orchardTreePoints)
    if (removed.scope === 'orchard') {
      for (const treeId of affectedIds) {
        if (!(treeId in nextOverrides)) nextOverrides[treeId] = 'healthy'
      }
      persistOrchardTreeZones(
        'status',
        nextZones,
        persistentZoneReapplyUpdates('status', affectedIds, nextZones, orchardTreePoints, 'healthy'),
      )
    }
    setStatusZones(nextZones)
    setTreeOverrides(nextOverrides)
    setStatusZoneDraft([])
    setStatusZoneDrawing(false)
    setZoneHistory((current) => current.filter((entry) => (
      entry.type !== 'status' || entry.id !== zoneId
    )))
  }, [orchardTreePoints, persistOrchardTreeZones, statusZones])

  const handleStageZoneClear = useCallback(() => {
    if (!phenologyZones.length) return
    const savedZones = phenologyZones.filter((zone) => zone.scope === 'orchard')
    if (savedZones.length && !window.confirm('Delete all stage zones from this orchard?')) return
    const affectedIds = [...new Set(savedZones.flatMap((zone) => (
      treeIdsInPolygon(orchardTreePoints, zone.coordinates)
    )))]
    const resetStage = selectedOrchardRecord?.orchard_stage || 'mature'
    setPhenologyZones([])
    setTreeStageOverrides(Object.fromEntries(affectedIds.map((treeId) => [treeId, resetStage])))
    setStageZoneDraft([])
    setStageZoneDrawing(false)
    setZoneHistory((current) => current.filter((entry) => entry.type !== 'stage'))
    if (savedZones.length) {
      persistOrchardTreeZones('stage', [], affectedIds.length ? [{
        treeIds: affectedIds,
        patch: { stage: resetStage },
      }] : [])
    }
  }, [
    orchardTreePoints,
    persistOrchardTreeZones,
    phenologyZones,
    selectedOrchardRecord?.orchard_stage,
  ])

  const handleStatusZoneClear = useCallback(() => {
    if (!statusZones.length) return
    const savedZones = statusZones.filter((zone) => zone.scope === 'orchard')
    if (savedZones.length && !window.confirm('Delete all status zones from this orchard?')) return
    const affectedIds = [...new Set(savedZones.flatMap((zone) => (
      treeIdsInPolygon(orchardTreePoints, zone.coordinates)
    )))]
    setStatusZones([])
    setTreeOverrides(Object.fromEntries(affectedIds.map((treeId) => [treeId, 'healthy'])))
    setStatusZoneDraft([])
    setStatusZoneDrawing(false)
    setZoneHistory((current) => current.filter((entry) => entry.type !== 'status'))
    if (savedZones.length) {
      persistOrchardTreeZones('status', [], affectedIds.length ? [{
        treeIds: affectedIds,
        patch: { status: 'healthy' },
      }] : [])
    }
  }, [orchardTreePoints, persistOrchardTreeZones, statusZones])

  const handleManagementZoneStart = useCallback(() => {
    setStageZoneDraft([])
    setStageZoneDrawing(false)
    setStatusZoneDraft([])
    setStatusZoneDrawing(false)
    setCecidZoneDraft([])
    setCecidZoneEditingId(null)
    setCecidZoneDrawing(false)
    setManagementZoneDraft([])
    setManagementZoneEditingId(null)
    setManagementZoneLabel(`Zone ${managementZones.length + 1}`)
    setManagementZoneDrawing(true)
  }, [managementZones.length])

  const handleManagementZoneCancel = useCallback(() => {
    setManagementZoneDraft([])
    setManagementZoneEditingId(null)
    setManagementZoneDrawing(false)
  }, [])

  const handleManagementZoneMapClick = useCallback((coordinate) => {
    setManagementZoneDraft((current) => [...current, coordinate])
  }, [])

  const handleManagementZoneUndoPoint = useCallback(() => {
    setManagementZoneDraft((current) => current.slice(0, -1))
  }, [])

  const handleManagementZoneFinish = useCallback(() => {
    if (managementZoneDraft.length < 3) return
    const treeCount = treeIdsInPolygon(orchardTreePoints, managementZoneDraft).length
    const newZone = {
      id: managementZoneEditingId || `management-zone-${Date.now()}`,
      label: managementZoneLabel.trim() || `Zone ${managementZones.length + 1}`,
      coordinates: managementZoneDraft,
      tree_count: treeCount,
    }
    const otherZones = managementZones.filter((zone) => zone.id !== managementZoneEditingId)
    const overlaps = overlappingManagementZones(newZone, otherZones, orchardTreePoints)
    if (overlaps.length) {
      setManagementZoneSaveState('error')
      setManagementZoneSaveError(
        `Selected trees already belong to ${overlaps.map((zone) => zone.label).join(', ')}. Adjust the boundary so reporting zones do not share trees.`,
      )
      return
    }
    const nextZones = managementZoneEditingId
      ? managementZones.map((zone) => (zone.id === managementZoneEditingId ? { ...zone, ...newZone } : zone))
      : [...managementZones, newZone]
    persistManagementZones(nextZones)
    setManagementZoneDraft([])
    setManagementZoneEditingId(null)
    setManagementZoneDrawing(false)
  }, [
    managementZoneDraft,
    managementZoneEditingId,
    managementZoneLabel,
    managementZones,
    orchardTreePoints,
    persistManagementZones,
  ])

  const handleManagementZoneRedraw = useCallback((zoneId) => {
    const zone = managementZones.find((candidate) => candidate.id === zoneId)
    if (!zone) return
    setStageZoneDrawing(false)
    setStageZoneDraft([])
    setStatusZoneDrawing(false)
    setStatusZoneDraft([])
    setCecidZoneDrawing(false)
    setCecidZoneDraft([])
    setCecidZoneEditingId(null)
    setManagementZoneLabel(zone.label)
    setManagementZoneDraft([])
    setManagementZoneEditingId(zone.id)
    setManagementZoneDrawing(true)
  }, [managementZones])

  const handleManagementZoneUpdate = useCallback((zoneId, patch) => {
    persistManagementZones(managementZones.map((zone) => (
      zone.id === zoneId ? { ...zone, ...patch } : zone
    )))
  }, [managementZones, persistManagementZones])

  const handleManagementZoneDelete = useCallback((zoneId) => {
    persistManagementZones(managementZones.filter((zone) => zone.id !== zoneId))
    if (managementZoneEditingId === zoneId) handleManagementZoneCancel()
  }, [handleManagementZoneCancel, managementZoneEditingId, managementZones, persistManagementZones])

  const handleManagementZoneClear = useCallback(() => {
    if (!managementZones.length) return
    if (!window.confirm('Delete all named management zones from this orchard?')) return
    persistManagementZones([])
    handleManagementZoneCancel()
  }, [handleManagementZoneCancel, managementZones.length, persistManagementZones])

  const handleCecidZoneStart = useCallback(() => {
    setStageZoneDraft([])
    setStageZoneDrawing(false)
    setStatusZoneDraft([])
    setStatusZoneDrawing(false)
    setManagementZoneDraft([])
    setManagementZoneEditingId(null)
    setManagementZoneDrawing(false)
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
    const treeCount = treeIdsInPolygon(orchardTreePoints, cecidZoneDraft).length
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

  // ── Unified zone undo / clear ─────────────────────────────────────────
  const handleZoneUndoLast = useCallback(() => {
    if (!zoneHistory.length) return
    const last = zoneHistory[zoneHistory.length - 1]
    if (last.type === 'stage') {
      handleStageZoneDelete(last.id)
    } else if (last.type === 'status') {
      handleStatusZoneDelete(last.id)
    } else {
      handleCecidZoneDelete(last.id)
    }
  }, [
    handleCecidZoneDelete,
    handleStageZoneDelete,
    handleStatusZoneDelete,
    zoneHistory,
  ])

  const handleZoneClearAll = useCallback(async () => {
    const savedStageZones = phenologyZones.filter((zone) => zone.scope === 'orchard')
    const savedStatusZones = statusZones.filter((zone) => zone.scope === 'orchard')
    const stageIds = [...new Set(savedStageZones.flatMap((zone) => (
      treeIdsInPolygon(orchardTreePoints, zone.coordinates)
    )))]
    const statusIds = [...new Set(savedStatusZones.flatMap((zone) => (
      treeIdsInPolygon(orchardTreePoints, zone.coordinates)
    )))]
    const resetStage = selectedOrchardRecord?.orchard_stage || 'mature'
    setPhenologyZones([])
    setTreeStageOverrides(Object.fromEntries(stageIds.map((treeId) => [treeId, resetStage])))
    setStageZoneDraft([])
    setStageZoneDrawing(false)
    setStatusZones([])
    setTreeOverrides(Object.fromEntries(statusIds.map((treeId) => [treeId, 'healthy'])))
    setStatusZoneDraft([])
    setStatusZoneDrawing(false)
    if (savedStageZones.length) {
      await persistOrchardTreeZones('stage', [], stageIds.length ? [{
        treeIds: stageIds,
        patch: { stage: resetStage },
      }] : [])
    }
    if (savedStatusZones.length) {
      await persistOrchardTreeZones('status', [], statusIds.length ? [{
        treeIds: statusIds,
        patch: { status: 'healthy' },
      }] : [])
    }
    if (managementZones.length) persistManagementZones([])
    setManagementZoneDraft([])
    setManagementZoneEditingId(null)
    setManagementZoneDrawing(false)
    if (cecidWeedZones.length) persistCecidWeedZones([])
    setCecidZoneDraft([])
    setCecidZoneEditingId(null)
    setCecidZoneDrawing(false)
    setZoneHistory([])
  }, [
    orchardTreePoints,
    phenologyZones,
    statusZones,
    cecidWeedZones.length,
    managementZones.length,
    persistOrchardTreeZones,
    persistCecidWeedZones,
    persistManagementZones,
    selectedOrchardRecord?.orchard_stage,
  ])

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
                  treePoints={orchardTreePoints}
                  alerts={mapAlerts}
                  treeOverrides={treeOverrides}
                  stageOverrides={treeStageOverrides}
                  stageZones={phenologyZones}
                  stageZoneDrawing={stageZoneDrawing}
                  stageZoneStage={stageZoneStage}
                  stageZoneDraft={stageZoneDraft}
                  stageZoneSelectedCount={stageZoneSelectedCount}
                  stageOptions={PHENOLOGY_STAGE_OPTIONS}
                  onStageZoneStageChange={setStageZoneStage}
                  onStageZoneStart={handleStageZoneStart}
                  onStageZoneCancel={handleStageZoneCancel}
                  onStageZoneFinish={handleStageZoneFinish}
                  onStageZoneUndoPoint={handleStageZoneUndoPoint}
                  onStageZoneMapClick={handleStageZoneMapClick}
                  onStageZoneDraftChange={setStageZoneDraft}
                  onStageZoneDelete={handleStageZoneDelete}
                  onStageZoneClear={handleStageZoneClear}
                  statusZones={statusZones}
                  statusZoneDrawing={statusZoneDrawing}
                  statusZoneStatus={statusZoneStatus}
                  statusZoneDraft={statusZoneDraft}
                  statusZoneSelectedCount={statusZoneSelectedCount}
                  statusOptions={STATUS_ZONE_OPTIONS}
                  onStatusZoneStatusChange={setStatusZoneStatus}
                  onStatusZoneStart={handleStatusZoneStart}
                  onStatusZoneCancel={handleStatusZoneCancel}
                  onStatusZoneFinish={handleStatusZoneFinish}
                  onStatusZoneUndoPoint={handleStatusZoneUndoPoint}
                  onStatusZoneMapClick={handleStatusZoneMapClick}
                  onStatusZoneDraftChange={setStatusZoneDraft}
                  onStatusZoneDelete={handleStatusZoneDelete}
                  onStatusZoneClear={handleStatusZoneClear}
                  treeEditScope={treeEditScope}
                  treeEditSaveState={treeEditSaveState}
                  treeEditSaveError={treeEditSaveError}
                  onTreeEditScopeChange={setTreeEditScope}
                  managementZones={managementZones}
                  managementZoneDrawing={managementZoneDrawing}
                  managementZoneLabel={managementZoneLabel}
                  managementZoneDraft={managementZoneDraft}
                  managementZoneSelectedCount={managementZoneSelectedCount}
                  managementZoneSaveState={managementZoneSaveState}
                  managementZoneSaveError={managementZoneSaveError}
                  onManagementZoneLabelChange={setManagementZoneLabel}
                  onManagementZoneStart={handleManagementZoneStart}
                  onManagementZoneCancel={handleManagementZoneCancel}
                  onManagementZoneFinish={handleManagementZoneFinish}
                  onManagementZoneUndoPoint={handleManagementZoneUndoPoint}
                  onManagementZoneMapClick={handleManagementZoneMapClick}
                  onManagementZoneDraftChange={setManagementZoneDraft}
                  onManagementZoneUpdate={handleManagementZoneUpdate}
                  onManagementZoneRedraw={handleManagementZoneRedraw}
                  onManagementZoneDelete={handleManagementZoneDelete}
                  onManagementZoneClear={handleManagementZoneClear}
                  onManagementZoneRetry={retryManagementZoneSave}
                  cecidWeedZones={cecidWeedZones}
                  legacyCecidEmergenceZones={legacyCecidEmergenceZones}
                  cecidZoneDrawing={cecidZoneDrawing}
                  cecidZoneDensity={cecidZoneDensity}
                  cecidZoneLabel={cecidZoneLabel}
                  cecidZoneDraft={cecidZoneDraft}
                  cecidZoneSelectedCount={cecidZoneSelectedCount}
                  cecidZoneSaveState={cecidZoneSaveState}
                  cecidZoneSaveError={cecidZoneSaveError}
                  onCecidZoneDensityChange={setCecidZoneDensity}
                  onCecidZoneLabelChange={setCecidZoneLabel}
                  onCecidZoneStart={handleCecidZoneStart}
                  onCecidZoneCancel={handleCecidZoneCancel}
                  onCecidZoneFinish={handleCecidZoneFinish}
                  onCecidZoneUndoPoint={handleCecidZoneUndoPoint}
                  onCecidZoneMapClick={handleCecidZoneMapClick}
                  onCecidZoneDraftChange={setCecidZoneDraft}
                  onCecidZoneUpdate={handleCecidZoneUpdate}
                  onCecidZoneRedraw={handleCecidZoneRedraw}
                  onCecidZoneDelete={handleCecidZoneDelete}
                  onCecidZoneClear={handleCecidZoneClear}
                  onCecidZoneRetry={retryCecidWeedZoneSave}
                  selectedPestType={selectedPestType}
                  resultPestType={simData?.pest_type ?? selectedPestType}
                  zoneHistory={zoneHistory}
                  onZoneUndoLast={handleZoneUndoLast}
                  onZoneClearAll={handleZoneClearAll}
                  orchardName={orchardName}
                  orthophotoOverlay={orchardOrthophoto}
                  viewportKey={`${selectedOrchardId}:${mapRefreshKey}`}
                  fitToOrthophoto
                  currentFrame={displayedFrame}
                  cecidMapMode={cecidMapMode}
                  cecidEnsembleRuns={cecidLikelihoodAvailable ? cecidEnsembleRuns : 0}
                  onCecidMapModeChange={handleCecidMapModeChange}
                  onTreeClick={handleTreeClick}
                  onPrintReport={simData ? () => handleOpenSimulationReport(simData, true) : null}
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
                  onPrintRun={handleOpenSimulationReport}
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
          onPrintReport={simData ? () => handleOpenSimulationReport(simData, true) : null}
          orchardOrthophoto={orchardOrthophoto}
          orchards={orchards}
          selectedOrchardId={selectedOrchardId}
          onOrchardSelect={handleOrchardSelect}
          onOrchardRefresh={handleOrchardRefresh}
          onOrchardUpload={handleOrchardUpload}
          onOrchardStageChange={handleOrchardStageChange}
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
          statusZones={statusZones}
          treeStageOverrides={treeStageOverrides}
          phenologyZones={phenologyZones}
          managementZones={managementZones}
          cecidWeedZones={cecidWeedZones}
          legacyCecidEmergenceZones={legacyCecidEmergenceZones}
          selectedPestType={selectedPestType}
          onPestTypeChange={setSelectedPestType}
          onClearTreeStageOverrides={handleStageZoneClear}
          onSimulationComplete={handleSimulationComplete}
          simulationTemplate={simulationTemplate}
          playbackFrames={playbackFrames}
          currentFrameIdx={currentFrameIdx}
          onFrameSeek={handleFrameSeek}
          decisionMetrics={decisionMetrics}
          suggestedSimParams={suggestedSimParams}
          onClearSuggestedSimParams={() => setSuggestedSimParams(null)}
          activeWorkflow={sidebarWorkflow}
          onWorkflowChange={setSidebarWorkflow}
          collapsed={sidebarCollapsed}
          onCollapsedChange={setSidebarCollapsed}
          mobileOpen={sidebarMobileOpen}
          onMobileOpenChange={setSidebarMobileOpen}
          observationTreeIds={observationPrefill.treeIds}
          observationForecastRisk={observationPrefill.forecastRisk}
          observationForecastLeadHours={observationPrefill.forecastLeadHours}
          observationLon={observationPrefill.lon}
          observationLat={observationPrefill.lat}
          currentSimulationRunId={currentSimulationRunId}
        />
      </div>

      {/* ── Tree Management Modal ── */}
      {reportRequest && <SimulationReportModal {...reportRequest} onClose={handleCloseSimulationReport} />}

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
                <button
                  type="button"
                  className="btn btn-outline-success btn-sm w-100 mb-3"
                  onClick={handleOpenTreeVerification}
                >
                  <i className="bi bi-clipboard2-check me-1" />
                  Log field verification for this tree
                </button>
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
