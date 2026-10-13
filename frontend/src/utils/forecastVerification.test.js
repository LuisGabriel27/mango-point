import test from 'node:test'
import assert from 'node:assert/strict'
import { forecastVerificationContext, verificationNumber, verificationPredictionFields } from './forecastVerification.js'

const run = { run_id: 'forecast-a', orchard_id: 'orchard-a', pest_type: 'cecid', status: 'completed',
  risk_geojson: { features: [{ properties: { tree_id: 'tree-a', risk: 0.75 } }] } }

test('verification requires an identified completed forecast with a saved map for this orchard', () => {
  for (const candidate of [null, {}, { ...run, run_id: null }, { ...run, risk_geojson: null }, { ...run, status: 'running' }]) {
    assert.equal(forecastVerificationContext(candidate, 'orchard-a').available, false)
  }
  assert.equal(forecastVerificationContext(run, 'orchard-b').available, false)
  assert.equal(forecastVerificationContext({ ...run, orchard_id: null }, 'orchard-a').available, false)
  assert.equal(forecastVerificationContext({ ...run, pest_type: null }, 'orchard-a').available, false)
  assert.deepEqual(forecastVerificationContext(run, 'orchard-a'),
    { available: true, runId: 'forecast-a', orchardId: 'orchard-a', pest: 'cecid' })
})

test('saved request/metadata identifiers support loaded results and preserve the forecast pest', () => {
  const saved = { ...run, run_id: null, orchard_id: null, pest_type: null,
    metadata: JSON.stringify({ run_id: 'saved-forecast', pest_type: 'fruitfly' }),
    request_payload: JSON.stringify({ orchard_id: 'orchard-a' }) }
  assert.deepEqual(forecastVerificationContext(saved, 'orchard-a'),
    { available: true, runId: 'saved-forecast', orchardId: 'orchard-a', pest: 'fruitfly' })
})

test('tree-specific predictions cannot carry over to another tree or every tree in a bulk record', () => {
  const fields = { risk: 0.75, hour: 12, lon: 122.5, lat: 10.5 }
  assert.deepEqual(verificationPredictionFields(['a'], ['a'], fields),
    { forecast_risk: 0.75, forecast_lead_hours: 12, lon: 122.5, lat: 10.5 })
  for (const ids of [['b'], ['a', 'b'], []]) {
    assert.deepEqual(verificationPredictionFields(ids, ['a'], fields),
      { forecast_risk: null, forecast_lead_hours: null, lon: null, lat: null })
  }
})

test('missing prediction values stay unknown while valid zero values remain zero', () => {
  for (const value of [null, undefined, '', 'invalid']) assert.equal(verificationNumber(value), null)
  assert.equal(verificationNumber(0), 0)
  assert.deepEqual(verificationPredictionFields(['a'], ['a'], { risk: 0, hour: null, lon: null, lat: null }),
    { forecast_risk: 0, forecast_lead_hours: null, lon: null, lat: null })
})
