import assert from 'node:assert/strict'
import test from 'node:test'

import {
  cecidForecastContext,
  prepareAlertSimulationSuggestion,
} from './alertSimulation.js'

test('live forecast alerts prepare controls without starting a simulation', () => {
  const prepared = prepareAlertSimulationSuggestion({
    pest_type: 'cecid',
    orchard_id: 'orchard-a',
    orchard_stage: 'fruitlet',
    hours: 48,
    weather_mode: 'live',
    auto_run: true,
    manual_weather: { rainfall_mm: 10 },
    manual_weather_prefix_rain: [8],
    _forecast_summary: 'Favorable dawn window detected.',
  })

  assert.equal(prepared.useLiveWeather, true)
  assert.equal(prepared.orchardId, 'orchard-a')
  assert.equal(prepared.params.auto_run, false)
  assert.equal('manual_weather' in prepared.params, false)
  assert.equal('manual_weather_prefix_rain' in prepared.params, false)
  assert.equal(prepared.summary, 'Favorable dawn window detected.')
})

test('alert hours are bounded to the supported simulation range', () => {
  assert.equal(prepareAlertSimulationSuggestion({ hours: 999 }).params.hours, 168)
  assert.equal(prepareAlertSimulationSuggestion({ hours: 0 }).params.hours, 1)
  assert.equal(prepareAlertSimulationSuggestion({ hours: 'bad' }).params.hours, 48)
})

test('Cecid forecast context accepts current and compatible payload shapes', () => {
  const context = { peak_suitability: 0.72 }
  assert.deepEqual(cecidForecastContext({
    suggested_simulation_params: { cecid_forecast_context: context },
  }), context)
  assert.deepEqual(cecidForecastContext({
    suggested_simulation_params: { pest_type: 'cecid', forecast_context: context },
  }), context)
  assert.equal(cecidForecastContext({
    suggested_simulation_params: { pest_type: 'fruitfly', forecast_context: context },
  }), null)
})
