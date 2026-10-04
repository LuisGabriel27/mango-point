import { geometryCenter } from './mapGeometry.js'
import { buildZoneInventory } from './zoneInventory.js'
import { pointInPolygon } from './zoneSelection.js'
import { interpretCecidTree } from './cecidMapInterpretation.js'
import { normalizeManagementZones } from './managementZones.js'
import { normalizeCecidWeedZones } from './cecidWeedZones.js'
import { calculateSimulationEconomicImpact, formatPhp } from './economicImpact.js'

const EMPTY = { type: 'FeatureCollection', features: [] }
export const REPORT_RISK_LEGEND = [
  ['#b91c1c', 'Critical: 75–100%'], ['#ef4444', 'Severe: 50–<75%'],
  ['#f59e0b', 'High: 25–<50%'], ['#facc15', 'Moderate: 10–<25%'], ['#22c55e', 'Low: <10%'],
]
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

export function buildSimulationReport(run, { orchard = {}, selection = 'final', displayed = null, generatedAt = new Date().toISOString() } = {}) {
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
  const hasEnsemble = pest === 'cecid' && geojson.features.some((feature) => Number(feature.properties?.ensemble_runs) > 1)
  const mapMode = useDisplayed ? displayed.mode || 'representative' : hasEnsemble ? 'likelihood' : 'representative'
  const frame = useDisplayed ? displayed.frame : lastFrame
  const hour = frame?.hour ?? null
  const orchardId = result.orchard_id ?? request.orchard_id ?? orchard.orchard_id ?? 'default-orchard'
  const baseGeojson = parse(request.orchard_geojson, null) ?? orchard.geojson ?? EMPTY
  const treePoints = (baseGeojson.features || []).map((feature, index) => {
    const center = geometryCenter(feature.geometry)
    return center ? { tree_id: feature.properties?.tree_id ?? feature.id ?? index, lon: center[0], lat: center[1] } : null
  }).filter(Boolean)
  const stageZones = zones(dashboard.phenology_zones ?? request.phenology_zones)
  const statusZones = zones(dashboard.status_zones)
  const managementZones = normalizeManagementZones(request.management_zones ?? dashboard.management_zones ?? metadata.management_zones)
  const cecidWeedZones = normalizeCecidWeedZones(request.cecid_weed_zones ?? dashboard.cecid_weed_zones ?? metadata.cecid_weed_zones)
  const legacyCecidEmergenceZones = zones(request.cecid_emergence_zones ?? dashboard.cecid_emergence_zones)
  const features = geojson.features.map((feature) => {
    const properties = feature.properties || {}
    const interpreted = pest === 'cecid' ? interpretCecidTree(properties, mapMode) : null
    return {
      center: geometryCenter(feature.geometry),
      risk: interpreted?.eligible === false ? 0 : number(interpreted?.displayRisk ?? properties.risk),
      state: String(properties.state ?? properties.status ?? '').toLowerCase(),
    }
  })
  const unit = (result.simulation_mode ?? metadata.simulation_mode ?? request.simulation_mode) === 'tree_graph' ? 'trees' : 'cells'
  const peak = maximum(features.map((feature) => feature.risk))
  const infested = number(useDisplayed && frame ? frame.n_infested : result.n_infested_final)
  const economic = calculateSimulationEconomicImpact(result, { infestedCount: infested })
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
    ?? (request.manual_weather || request.manual_weather_blocks || request.manual_weather_series ? 'Saved manual weather' : 'Saved forecast weather')
  const label = `${useDisplayed ? 'Displayed result' : 'Final result'}${hour != null ? ` · Hour ${hour}` : ''}`
  return {
    runId: result.run_id ?? metadata.run_id ?? 'Unrecorded run', orchardId,
    orchardName: savedOrchard.name || orchard.name || (orchardId === 'default-orchard' ? 'Default Orchard (BPI)' : orchardId),
    pestLabel: pest === 'cecid' ? 'Cecid Fly' : pest === 'fruitfly' ? 'Fruit Fly' : pest || 'Not recorded',
    pest, hours: result.hours ?? request.hours ?? metadata.hours, hour, label, mapMode,
    mapDescription: mapMode === 'likelihood' ? 'Infestation frequency across repeated runs' : 'Representative simulation result',
    generatedAt, startedAt: result.started_at ?? metadata.started_at,
    completedAt: result.completed_at ?? metadata.completed_at,
    modelVersion: metadata.model_version ?? dashboard.simulation_model_version ?? 'Not recorded',
    seed: result.random_seed ?? request.random_seed ?? metadata.random_seed ?? 'Not recorded',
    mode: result.simulation_mode ?? metadata.simulation_mode ?? request.simulation_mode ?? 'Not recorded',
    stage: metadata.orchard_stage ?? request.orchard_stage ?? 'Not recorded',
    daysFlowering: metadata.days_since_flowering ?? request.days_since_flowering,
    weatherSource: source, weather: frame?.weather ?? request.manual_weather ?? null,
    geojson, baseGeojson, orthophotoOverlay, stageZones, statusZones,
    managementZones, cecidWeedZones, legacyCecidEmergenceZones, zoneEntries,
    unit, total: features.length, peak, infested, economic,
    highRisk: features.filter((feature) => feature.risk != null && feature.risk >= 0.5).length,
    uncertainty: metadata.cecid_uncertainty_summary,
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
function embeddedImage(value) {
  return /^data:image\/(png|jpeg);base64,[a-zA-Z0-9+/=]+$/.test(value || '') ? value : ''
}

export function simulationReportHtml(report, snapshot, logo = '') {
  const mapImage = embeddedImage(snapshot?.dataUrl)
  if (!mapImage) throw new Error('A complete map image is required before the report can be exported.')
  const e = escapeReportHtml
  const value = (item) => item == null ? 'Not recorded' : e(item)
  const metric = (label, content) => `<div class="metric"><span>${e(label)}</span><strong>${value(content)}</strong></div>`
  const legend = (items) => items.map(([color, label]) => `<span><i style="background:${color}"></i>${e(label)}</span>`).join('')
  const imageLogo = embeddedImage(logo)
  const treeLegend = report.pest === 'cecid'
    ? [...REPORT_TREE_LEGEND, ['#6b7280', 'Not fruitlet eligible'], ['#78350f', 'S: soil source']]
    : REPORT_TREE_LEGEND
  const zonesHtml = report.zoneEntries.length ? `<table><thead><tr><th>Zone</th><th>Type / setting</th><th>Trees in area</th><th>Maximum map risk</th></tr></thead><tbody>${report.zoneEntries.map((entry) => `<tr><td>${e(entry.label)}</td><td>${e(entry.typeLabel)}${entry.detail ? ` · ${e(entry.detail)}` : ''}</td><td>${value(entry.treeCount)}</td><td>${reportPercent(entry.peakRisk)}</td></tr>`).join('')}</tbody></table>` : '<p>No zone boundaries were saved with this simulation.</p>'
  const weather = report.weather || {}
  const weatherRows = [
    ['Temperature (°C)', weather.temperature_c ?? weather.temp_c], ['Humidity (%)', weather.humidity],
    ['Rain (mm)', weather.rainfall_mm ?? weather.rain_mm], ['Wind (m/s)', weather.wind_speed_ms ?? weather.wind_ms],
  ].filter(([, field]) => field != null)
  const economicHtml = report.economic ? `<h2>Economic impact if recommendations are followed</h2><div class="metrics economic-metrics">${metric('Projected loss at risk', formatPhp(report.economic.projected_loss))}${metric('Potential savings', formatPhp(report.economic.estimated_savings))}${metric('Remaining loss after action', formatPhp(report.economic.remaining_loss))}${metric('Expected loss avoided', reportPercent(report.economic.recommendation_effectiveness))}</div><p class="muted">Planning estimate based on ${value(report.economic.infested_count)} affected ${e(report.unit)}, ${value(report.economic.yield_per_tree_kg)} kg yield per tree, PHP ${value(report.economic.farmgate_price_php_per_kg)} per kg and ${reportPercent(report.economic.damage_rate)} base damage. Treatment and labor costs are not subtracted.</p>` : ''
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>${e(report.orchardName)} — MangoPoint simulation report</title>
<style>
@page{size:A4 landscape;margin:10mm}*{box-sizing:border-box}body{font:12px/1.45 Arial,sans-serif;color:#172b24;margin:0;background:#eef3f0}.toolbar{padding:14px;text-align:center;background:#1b4332;color:white}.toolbar button{padding:10px 18px;border:0;border-radius:6px;font-weight:bold;cursor:pointer}.report{max-width:1100px;margin:20px auto;background:white;padding:24px}header{display:flex;align-items:center;gap:12px;border-bottom:3px solid #1b4332;padding-bottom:10px}header img{width:42px;height:42px;object-fit:contain}h1{font-size:22px;margin:0}h2{font-size:16px;margin:20px 0 6px}p{margin:5px 0}.muted{color:#50645b}.meta{display:grid;grid-template-columns:1fr 1fr;gap:4px 24px;margin:10px 0}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:12px 0}.metric{border:1px solid #afc2b6;border-radius:6px;padding:9px}.metric span{display:block;font-size:11px}.metric strong{display:block;font-size:19px}.map{display:block;width:100%;max-height:118mm;object-fit:contain;border:1px solid #b8c9bf;background:#f4f7f5}.legend{display:flex;flex-wrap:wrap;gap:4px 18px;margin:6px 0;font-size:10px}.legend span{display:inline-flex;align-items:center;gap:5px}.legend i{display:inline-block;width:11px;height:11px;border:1px solid #566b60;border-radius:50%}.caption{font-size:10px}.details{break-before:page}.settings{display:grid;grid-template-columns:1fr 1fr;gap:6px 24px}table{width:100%;border-collapse:collapse;font-size:11px;margin:10px 0}th,td{text-align:left;border:1px solid #bccbc3;padding:6px 8px}th{background:#edf3ef}thead{display:table-header-group}tr{break-inside:avoid}footer{margin-top:16px;border-top:1px solid #b7c8bd;padding-top:8px;font-size:10px}.notes{height:45px;border-bottom:1px solid #b7c8bd}@media print{body{background:white}.toolbar{display:none}.report{margin:0;padding:0;max-width:none}.metric,.map,th,.legend i{print-color-adjust:exact;-webkit-print-color-adjust:exact}h2{break-after:avoid}}@media(max-width:650px){.report{padding:12px}.meta,.settings{grid-template-columns:1fr}.metrics{grid-template-columns:1fr 1fr}}
</style></head><body><div class="toolbar"><button type="button" onclick="window.print()">Print / Save as PDF</button> <span>This report includes its map and can be opened offline.</span></div><main class="report">
<header>${imageLogo ? `<img src="${imageLogo}" alt="MangoPoint">` : ''}<div><h1>MangoPoint · Simulation report</h1><strong>${e(report.orchardName)}</strong></div></header>
<div class="meta"><div><strong>${e(report.label)}</strong> · ${e(report.mapDescription)}</div><div>Pest: <strong>${e(report.pestLabel)}</strong> · Duration: ${value(report.hours)} h</div><div>Simulation started: ${reportDate(report.startedAt)} (Philippine time)</div><div>Run: ${e(report.runId)}</div></div>
<div class="metrics">${metric(`Infested ${report.unit}${report.mapMode === 'likelihood' ? ' (representative run)' : ''}`, report.infested)}${metric('Maximum map risk', reportPercent(report.peak))}${metric(`${report.unit} at ≥50% map risk`, report.highRisk)}${metric(`Total simulated ${report.unit}`, report.total)}</div>
<img class="map" src="${mapImage}" alt="${e(report.label)} map with simulation heatmap, tree markers and zone outlines">
<div class="caption">${e(snapshot.attribution)} · North is up. Zone outlines use the simulation’s saved inputs.</div>
<strong>${report.mapMode === 'likelihood' ? 'Infestation frequency across runs' : 'Map risk level'}</strong><div class="legend">${legend(REPORT_RISK_LEGEND)}</div>
<strong>Tree state / markers</strong><div class="legend">${legend(treeLegend)}</div><p class="caption muted">Tree markers use risk colors when risk is available; bagged and dead trees retain their state colors. This is a simulated forecast, not a field observation.</p>
<section class="details"><h2>Simulation record</h2><div class="settings"><div>Orchard: ${e(report.orchardName)} (${e(report.orchardId)})</div><div>Model: ${e(report.modelVersion)}</div><div>Simulation mode: ${e(report.mode)} · Seed: ${value(report.seed)}</div><div>Orchard stage: ${e(report.stage)} · Days since flowering: ${value(report.daysFlowering)}</div><div>Weather: ${e(report.weatherSource)}</div><div>Completed: ${reportDate(report.completedAt)} (Philippine time)</div></div>
${economicHtml}
${weatherRows.length ? `<h2>Weather at the reported hour</h2><div class="settings">${weatherRows.map(([label, field]) => `<div>${e(label)}: ${value(field)}</div>`).join('')}</div>` : ''}
<h2>Zones included in the map</h2>${zonesHtml}
${report.timeline.length ? `<h2>Simulation progression · sampled hours</h2><table><thead><tr><th>Hour</th><th>Infested ${e(report.unit)}</th><th>Newly infested ${e(report.unit)}</th></tr></thead><tbody>${report.timeline.map((frame) => `<tr><td>${value(frame.hour)}</td><td>${value(frame.n_infested)}</td><td>${value(frame.n_new)}</td></tr>`).join('')}</tbody></table>` : ''}
${number(report.uncertainty?.runs) > 1 ? `<p>${value(report.uncertainty.runs)} repeated runs: ${value(report.uncertainty.minimum)}–${value(report.uncertainty.maximum)} infested trees; median ${value(report.uncertainty.median)}. This scenario range is not a calibrated confidence interval.</p>` : ''}
<h2>Manager’s notes / follow-up</h2><div class="notes"></div><p>Reviewed by: ______________________________ &nbsp; Date: __________________</p></section>
<footer>Generated ${reportDate(report.generatedAt)} (Philippine time) · MangoPoint · Run ${e(report.runId)} · ${e(report.label)}</footer></main></body></html>`
}
