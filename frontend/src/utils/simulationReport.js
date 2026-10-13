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

export function summarizeReportSources(sources) {
  const groups = [
    { key: 'infected', label: 'Recorded / selected infected' },
    { key: 'history', label: 'History Infected' },
    { key: 'suspect', label: 'Suspect' },
    { key: 'assumed', label: 'Assumed / fallback' },
    { key: 'other', label: 'Other source inputs' },
  ].map((group) => ({ ...group, sources: [] }))
  for (const source of sources) {
    const status = String(source.status || '').toLowerCase()
    const origin = String(source.origin || '').toLowerCase()
    const key = status === 'history_infected' || origin === 'history_reservoir' ? 'history'
      : status === 'suspect' || origin === 'suspect_infection' ? 'suspect'
        : source.assumed === true || origin === 'assumed_fallback' ? 'assumed'
          : ['infected', 'infested'].includes(status) ? 'infected' : 'other'
    groups.find((group) => group.key === key).sources.push(source)
  }
  return groups.map((group) => ({ ...group, count: group.sources.length,
    active: group.sources.every((source) => typeof source.active === 'boolean')
      ? group.sources.filter((source) => source.active).length : null,
    ids: group.sources.map((source) => source.tree_id ?? source.id ?? source.source_id ?? 'Ground source'),
  }))
}
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

export function buildSimulationReport(run, { orchard = {}, selection = 'final', displayed = null, generatedAt = new Date().toISOString(), recordDetails = {}, includeDetails = false } = {}) {
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
    ?? (request.manual_weather || request.manual_weather_blocks?.length || request.manual_weather_series?.length ? 'Manual scenario' : 'Not recorded')
  const label = `${useDisplayed ? 'Displayed result' : 'Final result'}${hour != null ? ` · Hour ${hour}` : ''}`
  const initialSources = Array.isArray(metadata.initial_sources) ? metadata.initial_sources
    : Array.isArray(metadata.cecid_sources) ? metadata.cecid_sources : []
  const sourceSummary = summarizeReportSources(initialSources)
  const runCount = simulationUncertaintySummary({ metadata })?.runs
    ?? number(request.uncertainty_runs ?? request.cecid_uncertainty_runs)
    ?? Math.max(1, ...geojson.features.map((feature) => number(feature.properties?.ensemble_runs) ?? 1))
  const treatments = Array.isArray(request.treatment_applications) ? request.treatment_applications : []
  const weatherBlocks = Array.isArray(request.manual_weather_blocks) ? request.manual_weather_blocks : []
  const setting = (name, val, suffix = '') => [name, val == null ? 'Not recorded' : `${val}${suffix}`]
  const settings = [
    setting('Host stage', metadata.orchard_stage ?? request.orchard_stage),
    setting('Days since flowering', metadata.days_since_flowering ?? request.days_since_flowering),
    setting('Repeated runs', runCount), setting('Random seed', result.random_seed ?? request.random_seed ?? metadata.random_seed),
    setting('Weather source', source),
    setting('Outside pressure', request.neighbor_threat != null || metadata.neighbor_threat != null
      || Array.isArray(request.neighbor_sources) || Array.isArray(metadata.neighbor_sources)
      ? neighborPressureSummary(restoreNeighborSources({ ...request, ...metadata })) : null),
    setting('Treatment scenarios', Array.isArray(request.treatment_applications)
      ? treatments.length ? treatments.map((item) => `${item.treatment_type || 'Treatment'}${item.efficacy != null ? ` (${reportPercent(item.efficacy)} efficacy)` : ''}${item.source_reduction != null ? ` (${reportPercent(item.source_reduction)} source reduction)` : ''}`).join('; ') : 'None' : null),
    setting('Bagged tree inputs', Array.isArray(request.bagged_tree_ids)
      ? new Set([...request.bagged_tree_ids.map(String), ...Object.entries(request.tree_overrides || {}).filter(([, status]) => status === 'bagged').map(([id]) => id)]).size : null),
    setting('Observation seeds', typeof request.use_observations_as_seeds === 'boolean'
      ? request.use_observations_as_seeds ? `Enabled · ${request.observations_lookback_days ?? 'unspecified'} day lookback` : 'Disabled' : null),
  ]
  if (pest === 'cecid') {
    const soil = request.manual_soil_context
    const moisture = number(request.cecid_initial_soil_moisture_score ?? (soil?.preset === 'moist' ? soil.initial_moisture_score : null))
    settings.push(setting('Starting soil context', moisture != null ? `Assumed Hour 0 moisture ${reportPercent(moisture)}`
      : soil?.preset === 'dry' ? 'Dry preset' : soil?.preset === 'recently_wet' || soil?.preset === 'custom'
        ? `${soil.preset.replace(/_/g, ' ')} · ${soil.total_rain_mm ?? 'unspecified'} mm antecedent rain`
        : request.manual_weather_prefix_rain?.length ? 'Saved antecedent rain' : null))
  } else if ((result.simulation_mode ?? metadata.simulation_mode ?? request.simulation_mode) === 'tree_graph') {
    settings.push(setting('Graph link cutoff', metadata.tg_max_neighbor_dist_m ?? request.tg_max_neighbor_dist_m, ' m'))
  }
  const highRisk = features.filter((feature) => feature.risk != null && feature.risk >= 0.5).length
  const priorityIds = features.filter((feature) => feature.risk != null && feature.risk >= 0.5)
    .sort((a, b) => b.risk - a.risk).slice(0, 5).map((feature) => feature.id)
  // Field-check guidance is generated for the selected report frame. It never
  // claims that inspection or treatment has happened, or that map scores prove presence.
  const actions = [
    { title: highRisk ? 'Inspect the priority locations first' : 'Continue field monitoring', timing: 'Next field visit',
      detail: highRisk ? `${highRisk} ${unit} meet the report's 50% screening threshold. Start with IDs ${priorityIds.join(', ')}; confirm pest signs before intervention.`
        : 'No locations meet the report screening threshold. Inspect susceptible fruit and source locations; this does not establish pest absence.' },
    { title: pest === 'cecid' ? 'Check fruitlets and bagging' : 'Check mature fruit and sanitation', timing: 'After field confirmation',
      detail: pest === 'cecid' ? 'Inspect susceptible fruitlets, verify bagging coverage and record confirmed signs. Review source and soil assumptions before rerunning.'
        : 'Inspect mature/ripening fruit, traps and fallen fruit. Review bagging and sanitation around confirmed affected trees.' },
    { title: 'Record findings and review the scenario', timing: 'After inspection',
      detail: 'Log Present, Absent or Not inspected with the tree ID and date. Update inputs and rerun when weather, sources or management change. Use approved targeted control only after confirmation.' },
  ]
  return {
    runId: result.run_id ?? metadata.run_id ?? 'Unrecorded run', orchardId,
    orchardName: savedOrchard.name || orchard.name || (orchardId === 'default-orchard' ? 'Default Orchard (BPI)' : orchardId),
    pestLabel: pest === 'cecid' ? 'Fruit-attacking Cecid Fly' : pest === 'fruitfly' ? 'Oriental Fruit Fly' : pest || 'Not recorded',
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
    highRisk, sourceSummary, settings, actions, weatherBlocks, includeDetails,
    parameterOverrides: Object.entries({
      cecid_base_dispersal_prob: request.cecid_base_dispersal_prob,
      cecid_favorable_threshold: request.cecid_favorable_threshold,
      cecid_rainfall_threshold_mm: request.cecid_rainfall_threshold_mm,
      fruit_fly_base_dispersal_prob: request.fruit_fly_base_dispersal_prob,
      fruit_fly_temp_threshold_c: request.fruit_fly_temp_threshold_c,
      tg_lambda0: metadata.tg_lambda0 ?? request.tg_lambda0,
      tg_alpha: metadata.tg_alpha ?? request.tg_alpha,
      tg_beta: metadata.tg_beta ?? request.tg_beta,
      tg_wind_bias: metadata.tg_wind_bias ?? request.tg_wind_bias,
    }).filter(([, entry]) => entry != null),
    weatherInput: request.manual_weather ?? null,
    weatherSeriesCount: Array.isArray(request.manual_weather_series) ? request.manual_weather_series.length : null,
    uncertainty: simulationUncertaintySummary({ metadata }),
    initialSources,
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
