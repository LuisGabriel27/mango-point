function object(value) {
  if (typeof value !== 'string') return value || {}
  try { return JSON.parse(value) || {} } catch { return {} }
}

export function forecastVerificationContext(run, orchardId) {
  const metadata = object(run?.metadata)
  const request = object(run?.request_payload ?? run?.input_parameters)
  const runId = run?.run_id ?? metadata.run_id
  const map = run?.risk_geojson ?? run?.time_series?.at(-1)?.risk_geojson
  if (!runId || !map?.features?.length || (run.status && run.status !== 'completed')) {
    return { available: false, reason: 'Run a simulation or open History → Load Result before recording forecast verification.' }
  }
  const savedOrchardId = run.orchard_id ?? request.orchard_id ?? metadata.orchard_id
  if (!orchardId || savedOrchardId == null || String(savedOrchardId) !== String(orchardId)) {
    return { available: false, reason: 'Load a completed forecast for the selected orchard before recording verification.' }
  }
  const pest = run.pest_type ?? metadata.pest_type ?? request.pest_type
  if (!['cecid', 'fruitfly'].includes(pest)) {
    return { available: false, reason: 'This forecast has no recorded pest type. Run a new simulation before recording verification.' }
  }
  return { available: true, runId: String(runId), orchardId: String(savedOrchardId), pest }
}

export function verificationNumber(value) {
  return value != null && value !== '' && Number.isFinite(Number(value)) ? Number(value) : null
}

// Tree-specific prediction fields cannot be reused for a manually entered
// different tree or assigned to every tree in a bulk observation.
export function verificationPredictionFields(treeIds, selectedTreeIds, fields) {
  const sameTree = treeIds.length === 1 && selectedTreeIds.length === 1
    && String(treeIds[0]) === String(selectedTreeIds[0])
  return {
    forecast_risk: sameTree ? verificationNumber(fields.risk) : null,
    forecast_lead_hours: sameTree && verificationNumber(fields.hour) != null
      ? Math.max(0, Math.round(Number(fields.hour))) : null,
    lon: sameTree ? verificationNumber(fields.lon) : null,
    lat: sameTree ? verificationNumber(fields.lat) : null,
  }
}
