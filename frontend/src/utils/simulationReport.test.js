import test from 'node:test'
import assert from 'node:assert/strict'
import { buildSimulationReport, reportFilename, simulationReportHtml } from './simulationReport.js'
import { normalizeSimulationRunForHistory } from './simulationHistoryStore.js'

const feature = (id, risk, state = 'unbagged', extra = {}) => ({
  type: 'Feature', geometry: { type: 'Point', coordinates: [id, 1] },
  properties: { tree_id: String(id), risk, state, ...extra },
})
const geojson = (...features) => ({ type: 'FeatureCollection', features })
const zone = { id: 'area-1', label: 'North area', coordinates: [[0, 0], [3, 0], [3, 2], [0, 2]] }
const initial = { hour: 0, n_infested: 0, n_new: 0, risk_geojson: geojson(feature(1, 0)), weather: { temperature_c: 0, rainfall_mm: 0 } }
const final = { hour: 47, n_infested: 2, n_new: 1, risk_geojson: geojson(feature(1, 0.9, 'infested'), feature(2, 0.6, 'infested')) }
const run = {
  run_id: 'run-123', orchard_id: 'default-orchard', pest_type: 'fruitfly', hours: 48,
  simulation_mode: 'tree_graph', random_seed: 0, n_infested_final: 2,
  started_at: '2026-10-02T00:00:00Z', risk_geojson: final.risk_geojson,
  time_series: [initial, final], metadata: { model_version: 'test-model' },
  request_payload: {
    orchard_geojson: final.risk_geojson, management_zones: [zone],
    impact_assumptions: { yield_per_tree_kg: 45, farmgate_price_php_per_kg: 60, damage_base: 30 },
    dashboard_state: { report_orchard: { name: 'Recorded orchard' }, treatment_efficacy: 0.65, status_zones: [{ ...zone, id: 'status-1', status: 'infected' }] },
  },
}
const displayed = { geojson: initial.risk_geojson, frame: initial, mode: 'representative' }
const snapshot = { dataUrl: 'data:image/png;base64,AAAA', attribution: 'MapLibre · Tiles © Esri' }

test('reports preserve saved model assumptions without applying them to older runs', () => {
  const explanation = { source_rule: 'New fruit infestation does not create adult sources.', outside_pressure: '<outside estimate>' }
  const report = buildSimulationReport({ ...run, metadata: { ...run.metadata, model_interpretation: explanation } })
  assert.deepEqual(report.modelInterpretation, explanation)
  const html = simulationReportHtml(report, snapshot)
  assert.match(html, /New fruit infestation does not create adult sources/)
  assert.match(html, /&lt;outside estimate&gt;/)
  const legacyHtml = simulationReportHtml(buildSimulationReport(run), snapshot)
  assert.match(legacyHtml, /Detailed model assumptions were not recorded/)
  assert.doesNotMatch(legacyHtml, /New fruit infestation does not create adult sources/)
})

test('reports default to final results even while the live map displays hour zero', () => {
  const report = buildSimulationReport(run, { displayed })
  assert.equal(report.hour, 47)
  assert.equal(report.infested, 2)
  assert.equal(report.peak, 0.9)
  assert.equal(report.seed, 0)
  assert.equal(report.total, 2)
  assert.equal(report.economic.projected_loss, 1_620)
  assert.equal(report.economic.estimated_savings, 1_053)
})

test('displayed-hour reports use that frame for map, statistics and weather', () => {
  const report = buildSimulationReport(run, { displayed, selection: 'displayed' })
  assert.equal(report.hour, 0)
  assert.equal(report.infested, 0)
  assert.equal(report.peak, 0)
  assert.equal(report.total, 1)
  assert.equal(report.weather.temperature_c, 0)
  assert.equal(report.geojson, initial.risk_geojson)
  assert.equal(report.economic.projected_loss, 0)
})

test('saved input zones and orchard names stay attached to the run', () => {
  const report = buildSimulationReport(run, { orchard: { name: 'Renamed orchard', management_zones: [] } })
  assert.equal(report.orchardName, 'Recorded orchard')
  assert.equal(report.zoneEntries.length, 2)
  assert.equal(report.zoneEntries.find((entry) => entry.type === 'management').treeCount, 2)
  assert.equal(report.zoneEntries.find((entry) => entry.type === 'management').peakRisk, 0.9)
})

test('grid results are labeled as cells rather than trees', () => {
  const report = buildSimulationReport({ ...run, simulation_mode: 'grid' })
  assert.equal(report.unit, 'cells')
  assert.match(simulationReportHtml(report, snapshot), /Infested cells/)
})

test('Cecid final maps use ensemble frequency and keep representative totals labeled', () => {
  const report = buildSimulationReport({
    ...run, pest_type: 'cecid',
    risk_geojson: geojson(feature(1, 0.9, 'unbagged', { stage: 'fruitlet', ensemble_runs: 10, ensemble_infestation_frequency: 0.3, ensemble_infestation_count: 3 })),
  })
  assert.equal(report.mapMode, 'likelihood')
  assert.equal(report.peak, 0.3)
  assert.match(simulationReportHtml(report, snapshot), /Infested trees \(representative run\)/)
})

test('offline HTML embeds the map and logo, preserves attribution, and escapes user content', () => {
  const report = buildSimulationReport(run)
  report.orchardName = '<img src=x onerror=alert(1)>'
  const html = simulationReportHtml(report, snapshot, 'data:image/png;base64,AQID')
  assert.match(html, /src="data:image\/png;base64,AAAA"/)
  assert.match(html, /src="data:image\/png;base64,AQID"/)
  assert.match(html, /Tiles © Esri/)
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/)
  assert.doesNotMatch(html, /<img src=x/)
  assert.doesNotMatch(html, /(?:src|href)="https?:|@import|url\(/)
  assert.match(html, /size: A4 portrait/)
  assert.match(html, /window.print\(\)/)
  assert.match(html, /run-123/)
  assert.match(html, /Field observations \/ reviewer’s notes/)
  assert.match(html, /Crop impact · scenario planning estimate/)
  assert.match(html, /Potential savings/)
  assert.match(html, /PHP 1,053/)
  assert.match(html, /Treatment and labor costs are not subtracted/)
})

test('Fruit Fly final and displayed reports preserve their metric and sampled source assumptions', () => {
  const result = { ...run,
    risk_geojson: geojson(feature(1, 1, 'infested', { ensemble_runs: 5,
      ensemble_infestation_count: 1, ensemble_infestation_frequency: 0.2 })),
    metadata: { uncertainty_summary: { runs: 5, minimum: 0, median: 1, maximum: 2 },
      initial_sources: [{ tree_id: '1', status: 'history_infected', origin: 'history_reservoir',
        assumed: true, probability: 0.5, active: true }] },
    request_payload: { ...run.request_payload, history_source_probability: 0.5, suspect_source_probability: 0.75 },
  }
  const report = buildSimulationReport(result)
  assert.equal(report.mapMode, 'likelihood')
  assert.equal(report.peak, 0.2)
  assert.equal(report.uncertainty.runs, 5)
  const html = simulationReportHtml(report, snapshot)
  assert.match(html, /Infested trees \(representative run\)/)
  assert.match(html, /History Infected reservoir presence<\/dt><dd>50.0%/)
  assert.match(html, /Suspect current infection presence<\/dt><dd>75.0%/)
  assert.match(html, /history reservoir<small class="cell-note">Assumed presence/)
  assert.match(html, /50–&lt;75% of runs/)
  const one = buildSimulationReport(result, { selection: 'displayed', displayed: {
    geojson: result.risk_geojson, frame: final, mode: 'representative',
  } })
  assert.equal(one.mapMode, 'representative')
  assert.equal(one.peak, 1)
})

test('missing results or missing map images cannot silently create a blank report', () => {
  assert.throws(() => buildSimulationReport({}), /no saved map result/)
  assert.throws(() => simulationReportHtml(buildSimulationReport(run), { dataUrl: 'https://example.com/image.png' }), /complete map image/)
})

test('older runs fall back to their last saved frame without inventing a run date', () => {
  const report = buildSimulationReport({ ...run, risk_geojson: null, started_at: null })
  assert.equal(report.geojson, final.risk_geojson)
  assert.equal(report.startedAt, undefined)
  assert.match(simulationReportHtml(report, snapshot), /Run executed · Philippine time<\/dt><dd>Not recorded/)
  assert.doesNotMatch(reportFilename({ ...report, orchardName: '../Farm: west/area' }), /\.\.\//)
})

test('normalized legacy history preserves an unknown execution date and an unknown initial baseline', () => {
  const legacy = normalizeSimulationRunForHistory({ ...run, started_at: null })
  const report = buildSimulationReport(legacy)
  assert.equal(legacy.started_at, null)
  assert.ok(legacy.local_saved_at)
  assert.equal(report.startedAt, undefined)
  assert.equal(report.initialInfested, null)
  assert.equal(report.newlyInfested, null)
})

test('displayed final frequency keeps the final forecast date and weather with no playback frame', () => {
  const saved = { ...run, time_series: [initial, { ...final, datetime: '2026-10-03T08:00:00+08:00', weather: { wind_dir_deg: 270 } }] }
  const report = buildSimulationReport(saved, { selection: 'displayed', displayed: { geojson: final.risk_geojson, mode: 'likelihood', frame: null } })
  assert.equal(report.hour, 47)
  assert.equal(report.reportedAt, '2026-10-03T08:00:00+08:00')
  assert.equal(report.weather.wind_dir_deg, 270)
})

test('grid records do not invent a tree inventory or apply per-tree economics to cells', () => {
  const polygon = { ...feature(1, 0.9), geometry: { type: 'Polygon', coordinates: [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]] } }
  const report = buildSimulationReport({ ...run, simulation_mode: 'grid', request_payload: {
    ...run.request_payload, orchard_geojson: geojson(polygon),
  } })
  assert.equal(report.economic, null)
  assert.equal(report.zoneEntries[0].treeCount, null)
  const html = simulationReportHtml(report, snapshot)
  assert.doesNotMatch(html, /Potential savings|PHP 1,053/)
  assert.match(html, /simulated cells are not an individual-tree inventory/)
})

test('record fields are bounded, escaped, preserve lines and cannot inject print CSS', () => {
  const report = buildSimulationReport({ ...run, run_id: '</style><script>alert(1)</script>' }, { recordDetails: {
    reference: 'REF-2026-01', preparedBy: '<b>Manager</b>', organization: 'BPI',
    reviewedBy: 'Reviewer', fieldNotes: 'First observation\nSecond observation', plannedActions: 'x'.repeat(4000),
  } })
  const html = simulationReportHtml(report, snapshot)
  assert.equal(report.recordDetails.plannedActions.length, 3000)
  assert.match(html, /REF-2026-01/)
  assert.match(html, /&lt;b&gt;Manager&lt;\/b&gt;/)
  assert.match(html, /First observation\nSecond observation/)
  assert.match(html, /Reviewed by: Reviewer/)
  assert.doesNotMatch(html, /<script>|<b>Manager<\/b>/)
  assert.match(html, /counter\(page\).*counter\(pages\)/)
})

test('frequency distribution excludes dead and ineligible trees and separates report and model thresholds', () => {
  const report = buildSimulationReport({ ...run, n_infested_final: 1, metadata: { initial_infected_count: 1 },
    risk_geojson: geojson(
      feature(1, 1, 'infested', { stage: 'mature', ensemble_runs: 5, ensemble_infestation_frequency: 0.4 }),
      feature(2, 0.9, 'unbagged', { stage: 'mature', ensemble_runs: 5, ensemble_infestation_frequency: 0.8 }),
      feature(3, 1, 'dead', { stage: 'mature', ensemble_runs: 5, ensemble_infestation_frequency: 1 }),
      feature(4, 1, 'unbagged', { stage: 'fruitlet', ensemble_runs: 5, ensemble_infestation_frequency: 1 }),
    ), request_payload: { ...run.request_payload, risk_threshold: 0.7 },
  })
  assert.equal(report.peak, 0.8)
  assert.equal(report.highRisk, 1)
  assert.deepEqual(report.riskBands.map((band) => band.count), [1, 0, 1, 0, 0])
  assert.equal(report.unavailableRisk, 2)
  assert.deepEqual(report.priorityLocations.map((entry) => entry.id), ['2'])
  assert.equal(report.initialInfested, 1)
  assert.equal(report.newlyInfested, 0)
  assert.equal(report.simulationRiskThreshold, 0.7)
  assert.equal(report.priorityThreshold, 0.5)
})

test('legacy Cecid sources and saved synthetic weather provenance remain visible', () => {
  const report = buildSimulationReport({ ...run, pest_type: 'cecid', metadata: {
    cecid_sources: [{ tree_id: '1', label: 'Soil source', assumed: true }],
    weather_provenance: { provider: 'synthetic', fallback_reason: 'No saved forecast available', anchor_time: '2026-10-02T00:00:00Z' },
  } })
  assert.equal(report.initialSources.length, 1)
  const html = simulationReportHtml(report, snapshot)
  assert.match(html, /Soil source/)
  assert.match(html, /No saved forecast available/)
  assert.match(html, /Weather provider<\/dt><dd>synthetic/)
})
