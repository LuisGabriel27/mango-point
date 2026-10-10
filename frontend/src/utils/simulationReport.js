import { geometryCenter } from './mapGeometry.js'
import { buildZoneInventory } from './zoneInventory.js'
import { pointInPolygon } from './zoneSelection.js'
import { interpretCecidTree } from './cecidMapInterpretation.js'
import { interpretSimulationTree, simulationUncertaintySummary } from './simulationMapInterpretation.js'
import { normalizeManagementZones } from './managementZones.js'
import { normalizeCecidWeedZones } from './cecidWeedZones.js'
import { calculateSimulationEconomicImpact, formatPhp } from './economicImpact.js'
import { neighborPressureSummary, restoreNeighborSources } from './neighborSources.js'
import { RISK_LEGEND_ENTRIES } from './riskSurface.js'
import { renderSimulationReport } from './simulationReportTemplate.js'

const EMPTY = { type: 'FeatureCollection', features: [] }
export const REPORT_RISK_LEGEND = RISK_LEGEND_ENTRIES.map(({ color, label }) => [color, label])
export const REPORT_FREQUENCY_LEGEND = RISK_LEGEND_ENTRIES.map(({ color }, index) => [color,
  ['75–100% of runs', '50–<75% of runs', '25–<50% of runs', '10–<25% of runs', '<10% of runs'][index],
])
export const REPORT_TREE_LEGEND = [
  ['#22c55e', 'Healthy / unbagged'], ['#ef4444', 'Infested'], ['#3b82f6', 'Bagged'],
  ['#424242', 'Dead'], ['#ff9800', 'Historical'], ['#9c27b0', 'Suspect'],
]

function parse(value, fallback = {}) {
  if (typeof value !== 'string') return value ?? fallback
  try { return JSON.parse(value) } catch (_) { return fallback }
}
function zones(value) {
  const result = parse(value, [])
  return Array.isArray(result) ? result.filter((zone) => Array.isArray(zone?.coordinates)) : []
}
function number(value) {
  if (value == null || value === '') return null
  return Number.isFinite(Number(value)) ? Number(value) : null
}
function maximum(values) {
  const valid = values.filter((value) => value != null)
  return valid.length ? Math.max(...valid) : null
}
export function reportPercent(value) {
  const parsed = number(value)
  return parsed == null ? 'Not recorded' : `${(parsed * 100).toFixed(1)}%`
}
export function reportDate(value) {
  if (!value) return 'Not recorded'
  const date = new Date(value)
  if (!Number.isFinite(date.getTime())) return 'Not recorded'
  return date.toLocaleString('en-PH', {
    timeZone: 'Asia/Manila', year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

export function buildSimulationReport(run, { orchard = {}, selection = 'final', displayed = null, generatedAt = new Date().toISOString(), recordDetails = {} } = {}) {
  const result = { ...parse(run?.response_payload), ...run }
  const metadata = parse(result.metadata)
  const request = parse(result.request_payload ?? result.input_parameters)
  const dashboard = parse(request.dashboard_state)
  const savedOrchard = parse(dashboard.report_orchard)
  const frames = Array.isArray(result.time_series) ? result.time_series : []
  const lastFrame = frames.at(-1) ?? null
  const useDisplayed = selection === 'displayed' && displayed?.geojson?.features?.length
  const geojson = useDisplayed ? displayed.geojson : result.risk_geojson?.features?.length ? result.risk_geojson : lastFrame?.risk_geojson ?? EMPTY
  if (!geojson.features?.length) throw new Error('This simulation has no saved map result to print.')
  const pest = result.pest_type ?? request.pest_type ?? metadata.pest_type
  const hasEnsemble = geojson.features.some((feature) => Number(feature.properties?.ensemble_runs) > 1
    && feature.properties?.ensemble_infestation_frequency != null)
  const mapMode = useDisplayed ? displayed.mode || 'representative' : hasEnsemble ? 'likelihood' : 'representative'
  const frame = useDisplayed ? displayed.frame ?? lastFrame : lastFrame
  const hour = frame?.hour ?? null
  const orchardId = result.orchard_id ?? request.orchard_id ?? orchard.orchard_id ?? 'default-orchard'
  const baseGeojson = parse(request.orchard_geojson, null) ?? orchard.geojson ?? EMPTY
  const treePoints = (baseGeojson.features || []).filter((feature) => feature.geometry?.type === 'Point').map((feature, index) => {
    const center = geometryCenter(feature.geometry)
    return center ? { tree_id: feature.properties?.tree_id ?? feature.properties?.Tree_ID ?? feature.id ?? index, lon: center[0], lat: center[1] } : null
  }).filter(Boolean)
  const stageZones = zones(dashboard.phenology_zones ?? request.phenology_zones)
  const statusZones = zones(dashboard.status_zones)
  const managementZones = normalizeManagementZones(request.management_zones ?? dashboard.management_zones ?? metadata.management_zones)
  const cecidWeedZones = normalizeCecidWeedZones(request.cecid_weed_zones ?? dashboard.cecid_weed_zones ?? metadata.cecid_weed_zones)
  const legacyCecidEmergenceZones = zones(request.cecid_emergence_zones ?? dashboard.cecid_emergence_zones)
  const features = geojson.features.map((feature) => {
    const properties = feature.properties || {}
    const interpreted = pest === 'cecid' ? interpretCecidTree(properties, mapMode) : interpretSimulationTree(properties, mapMode)
    const state = String(properties.state ?? properties.status ?? properties.Status ?? '').toLowerCase()
    const stage = String(properties.stage ?? properties.Stage ?? '').toLowerCase()
    const eligible = !['dead', 'empty'].includes(state) && interpreted?.eligible !== false
      && !(pest === 'fruitfly' && stage && stage !== 'mature')
    return {
      id: properties.tree_id ?? properties.Tree_ID ?? feature.id ?? 'Not recorded',
      center: geometryCenter(feature.geometry),
      risk: eligible ? number(interpreted.displayRisk) : null,
      state, eligible,
    }
  })
  const unit = (result.simulation_mode ?? metadata.simulation_mode ?? request.simulation_mode) === 'tree_graph' ? 'trees' : 'cells'
  const peak = maximum(features.map((feature) => feature.risk))
  const infested = number(useDisplayed && frame ? frame.n_infested : result.n_infested_final)
    ?? features.filter((feature) => ['infested', 'infected'].includes(feature.state)).length
  // A cell count cannot be multiplied by per-tree crop values.
  const economic = unit === 'trees' ? calculateSimulationEconomicImpact(result, { infestedCount: infested }) : null
  const initialInfested = number(metadata.initial_infected_count ?? result.n_infested_initial)
  const riskBands = REPORT_RISK_LEGEND.map(([color, label], index) => ({
    color, label,
    count: features.filter((feature) => feature.risk != null
      && feature.risk >= [0.75, 0.5, 0.25, 0.1, 0][index]
      && (index === 0 || feature.risk < [1.01, 0.75, 0.5, 0.25, 0.1][index])).length,
  }))
  const details = Object.fromEntries(Object.entries({
    reference: 120, preparedBy: 160, organization: 200, reviewedBy: 160, fieldNotes: 3000, plannedActions: 3000,
  }).map(([key, limit]) => [key, String(recordDetails?.[key] ?? '').trim().slice(0, limit)]))
  const zoneEntries = buildZoneInventory({ stageZones, statusZones, managementZones, cecidWeedZones, legacyCecidEmergenceZones, treePoints: treePoints.length ? treePoints : null })
    .map((entry) => ({
      ...entry,
      peakRisk: maximum(features.filter((feature) => feature.center && pointInPolygon(feature.center, entry.zone.coordinates)).map((feature) => feature.risk)),
    }))
  const defaultOrchard = orchardId === 'default-orchard' || orchardId === 'guimaras-wonders-farm'
  const orthophotoOverlay = savedOrchard.orthophoto_overlay ?? (
    orchard.orthophoto_url && orchard.orthophoto_coordinates
      ? { url: orchard.orthophoto_url, coordinates: orchard.orthophoto_coordinates }
      : defaultOrchard ? null : false
  )
  const source = result.weather_source ?? result.history?.weather_source ?? metadata.weather_provenance?.source
    ?? (request.manual_weather || request.manual_weather_blocks || request.manual_weather_series ? 'Manual scenario' : 'Not recorded')
  const label = `${useDisplayed ? 'Displayed result' : 'Final result'}${hour != null ? ` · Hour ${hour}` : ''}`
  return {
    runId: result.run_id ?? metadata.run_id ?? 'Unrecorded run', orchardId,
    orchardName: savedOrchard.name || orchard.name || (orchardId === 'default-orchard' ? 'Default Orchard (BPI)' : orchardId),
    pestLabel: pest === 'cecid' ? 'Cecid Fly' : pest === 'fruitfly' ? 'Fruit Fly' : pest || 'Not recorded',
    pest, hours: result.hours ?? request.hours ?? metadata.hours, hour, label, mapMode,
    mapDescription: mapMode === 'likelihood' ? 'Infestation frequency across repeated runs' : 'Representative simulation result',
    generatedAt, recordDetails: details, startedAt: result.started_at ?? metadata.started_at,
    completedAt: result.completed_at ?? metadata.completed_at,
    modelVersion: metadata.model_version ?? dashboard.simulation_model_version ?? 'Not recorded',
    modelInterpretation: metadata.model_interpretation ?? null,
    seed: result.random_seed ?? request.random_seed ?? metadata.random_seed ?? 'Not recorded',
    mode: result.simulation_mode ?? metadata.simulation_mode ?? request.simulation_mode ?? 'Not recorded',
    stage: metadata.orchard_stage ?? request.orchard_stage ?? 'Not recorded',
    daysFlowering: metadata.days_since_flowering ?? request.days_since_flowering,
    neighborPressure: neighborPressureSummary(restoreNeighborSources({ ...request, ...metadata })),
    weatherSource: source, weather: frame?.weather ?? request.manual_weather ?? null,
    weatherProvenance: metadata.weather_provenance ?? {},
    forecastStart: frames[0]?.datetime ?? frames[0]?.weather?.datetime ?? request.manual_weather_series?.[0]?.datetime,
    forecastEnd: lastFrame?.datetime ?? lastFrame?.weather?.datetime,
    reportedAt: frame?.datetime ?? frame?.weather?.datetime,
    geojson, baseGeojson, orthophotoOverlay, stageZones, statusZones,
    managementZones, cecidWeedZones, legacyCecidEmergenceZones, zoneEntries,
    unit, total: features.length, peak, infested, initialInfested,
    newlyInfested: initialInfested == null ? null : Math.max(0, infested - initialInfested), economic,
    riskBands, unavailableRisk: features.filter((feature) => feature.risk == null).length,
    priorityThreshold: 0.5, simulationRiskThreshold: number(request.risk_threshold ?? metadata.risk_threshold),
    priorityLocations: features.filter((feature) => feature.risk != null && feature.risk >= 0.5)
      .sort((left, right) => right.risk - left.risk || String(left.id).localeCompare(String(right.id), 'en', { numeric: true }))
      .slice(0, 10),
    highRisk: features.filter((feature) => feature.risk != null && feature.risk >= 0.5).length,
    uncertainty: simulationUncertaintySummary({ metadata }),
    initialSources: Array.isArray(metadata.initial_sources) ? metadata.initial_sources
      : Array.isArray(metadata.cecid_sources) ? metadata.cecid_sources : [],
    sourceAssumptions: {
      history: number(request.history_source_probability ?? metadata.source_uncertainty_assumptions?.history_source_probability),
      suspect: number(request.suspect_source_probability ?? metadata.source_uncertainty_assumptions?.suspect_source_probability),
    },
    timeline: frames.filter((_entry, index) => (
      new Set([0, Math.floor((frames.length - 1) / 4), Math.floor((frames.length - 1) / 2), Math.floor(3 * (frames.length - 1) / 4), frames.length - 1]).has(index)
    )),
  }
}

export function escapeReportHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]))
}
export function reportFilename(report, extension = 'html') {
  return `MangoPoint-${report.orchardName}-${report.runId}-${report.hour == null ? 'final' : `hour-${report.hour}`}`.replace(/[^a-zA-Z0-9_-]+/g, '-').slice(0, 160) + `.${extension}`
}
export function simulationReportHtml(report, snapshot, logo = '') {
  return renderSimulationReport(report, snapshot, logo, {
    escapeReportHtml, reportPercent, reportDate, formatPhp,
    riskLegend: REPORT_RISK_LEGEND, frequencyLegend: REPORT_FREQUENCY_LEGEND, treeLegend: REPORT_TREE_LEGEND,
  })
}
