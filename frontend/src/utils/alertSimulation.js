const LIVE_MODE = 'live'

function normalizedHours(value) {
  const parsed = Number.parseInt(value, 10)
  if (!Number.isFinite(parsed)) return 48
  return Math.max(1, Math.min(168, parsed))
}

/**
 * Normalize an alert suggestion before it enters the simulation controls.
 * This helper intentionally has no execution side effect: an alert can only
 * prepare controls, while the SimulationCard Run button remains authoritative.
 */
export function prepareAlertSimulationSuggestion(rawParams) {
  const raw = rawParams && typeof rawParams === 'object' ? rawParams : {}
  const weatherMode = String(raw.weather_mode ?? '').toLowerCase()
  const useLiveWeather = weatherMode === LIVE_MODE
  const params = {
    ...raw,
    hours: normalizedHours(raw.hours),
    auto_run: false,
  }

  if (useLiveWeather) {
    delete params.manual_weather
    delete params.manual_weather_blocks
    delete params.manual_weather_series
    delete params.manual_weather_prefix_rain
    delete params.manual_soil_context
  }

  return {
    params,
    orchardId: raw.orchard_id == null ? null : String(raw.orchard_id),
    useLiveWeather,
    summary: String(
      raw._forecast_summary
      ?? raw._rain_summary
      ?? 'Forecast settings loaded. Review the controls, then press Run Simulation.',
    ),
  }
}

export function cecidForecastContext(alert) {
  const params = alert?.suggested_simulation_params
  const pest = String(params?.pest_type ?? '').toLowerCase().replace(/[-_ ]/g, '')
  const context = params?.cecid_forecast_context
    ?? (pest === 'cecid' || pest === 'cecidfly' ? params?.forecast_context : null)
  return context && typeof context === 'object' ? context : null
}
