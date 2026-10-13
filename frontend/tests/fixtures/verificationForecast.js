// Isolated browser fixtures, never submitted to a farm database.
export function verificationForecast({ runId = 'verification-sample', pest = 'cecid', mode = 'tree_graph', orchardId = 'default-orchard' } = {}) {
  const feature = (id, risk) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [122.5805 + id * 0.0001, 10.584] },
    properties: { tree_id: String(id), risk, state: 'unbagged', stage: pest === 'cecid' ? 'fruitlet' : 'mature' } })
  const geojson = { type: 'FeatureCollection', features: [feature(1, 0.8), feature(2, 0.2)] }
  const request = { pest_type: pest, orchard_id: orchardId, orchard_geojson: geojson, simulation_mode: mode,
    hours: 48, orchard_stage: pest === 'cecid' ? 'fruitlet' : 'mature', random_seed: 42 }
  return { run_id: runId, orchard_id: orchardId, pest_type: pest, simulation_mode: mode,
    status: 'completed', started_at: new Date().toISOString(), completed_at: new Date().toISOString(),
    hours: 48, random_seed: 42, peak_risk: 0.8, n_infested_final: 0, request_payload: request,
    metadata: { run_id: runId, pest_type: pest, simulation_mode: mode, model_version: 'isolated-browser-test' },
    risk_geojson: geojson, time_series: [{ hour: 47, n_infested: 0, n_new: 0,
      datetime: new Date().toISOString(), weather: { temperature_c: 28, rainfall_mm: 0, wind_speed_ms: 1 }, risk_geojson: geojson }] }
}
