import test from 'node:test'
import assert from 'node:assert/strict'
import { buildSimulationReport, reportFilename, simulationReportHtml } from './simulationReport.js'

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
  assert.match(html, /@page\{size:A4 landscape/)
  assert.match(html, /window.print\(\)/)
  assert.match(html, /run-123/)
  assert.match(html, /Manager’s notes/)
  assert.match(html, /Economic impact if recommendations are followed/)
  assert.match(html, /Potential savings/)
  assert.match(html, /PHP 1,053/)
  assert.match(html, /Treatment and labor costs are not subtracted/)
})

test('missing results or missing map images cannot silently create a blank report', () => {
  assert.throws(() => buildSimulationReport({}), /no saved map result/)
  assert.throws(() => simulationReportHtml(buildSimulationReport(run), { dataUrl: 'https://example.com/image.png' }), /complete map image/)
})

test('older runs fall back to their last saved frame without inventing a run date', () => {
  const report = buildSimulationReport({ ...run, risk_geojson: null, started_at: null })
  assert.equal(report.geojson, final.risk_geojson)
  assert.equal(report.startedAt, undefined)
  assert.match(simulationReportHtml(report, snapshot), /Simulation started: Not recorded/)
  assert.doesNotMatch(reportFilename({ ...report, orchardName: '../Farm: west/area' }), /\.\.\//)
})
