// Mirrors utils/daylight.py and utils/solar.py. These are scenario scales,
// not calibrated light thresholds for the fruit-attacking Cecid species.
export const DAYLIGHT_LIGHT_SPEC = Object.freeze({
  cloud_min_pct: 50, cloud_full_pct: 80,
  dim_brightness_ratio: 0.25, bright_brightness_ratio: 0.8,
  dni_reference_wm2: 800,
})
export const DAYLIGHT_CONDITIONS = Object.freeze({
  bright_sunshine: { label: 'Bright sunshine', score: 0 },
  intermittent_sunshine: { label: 'Intermittent sunshine', score: 0.5 },
  dim_overcast: { label: 'Dim overcast', score: 1 },
})
export const DAYLIGHT_WEATHER_FIELDS = [
  'shortwave_radiation_wm2', 'direct_normal_irradiance_wm2',
  'daylight_condition', 'daylight_condition_basis',
]
const clamp = (value) => Math.max(0, Math.min(1, value))
const radians = (degrees) => degrees * Math.PI / 180
function nonnegative(value) {
  if (value == null || value === '') return null
  const number = Number(value)
  return Number.isFinite(number) && number >= 0 ? number : null
}

export function normalizeDaylightWeather(value = {}) {
  const result = {}
  for (const key of DAYLIGHT_WEATHER_FIELDS.slice(0, 2)) {
    const number = nonnegative(value[key])
    if (number != null) result[key] = number
  }
  if (Object.hasOwn(DAYLIGHT_CONDITIONS, value.daylight_condition)) {
    result.daylight_condition = value.daylight_condition
    if (['observed', 'assumed'].includes(value.daylight_condition_basis)) {
      result.daylight_condition_basis = value.daylight_condition_basis
    }
  }
  return result
}

export function clearSkyShortwaveReference(value, latitude = 10.585, longitude = 122.58) {
  if (!(value instanceof Date) || Number.isNaN(value.getTime())) return null
  const local = new Date(value.getTime() + 8 * 3600000)
  const year = local.getUTCFullYear()
  const hour = local.getUTCHours() + local.getUTCMinutes() / 60 + local.getUTCSeconds() / 3600
  const dayNumber = Math.floor((Date.UTC(year, local.getUTCMonth(), local.getUTCDate()) - Date.UTC(year, 0, 0)) / 86400000)
  const yearLength = (Date.UTC(year + 1, 0, 1) - Date.UTC(year, 0, 1)) / 86400000
  const gamma = 2 * Math.PI / yearLength * (dayNumber - 1 + (hour - 12) / 24)
  const equation = 229.18 * (0.000075 + 0.001868 * Math.cos(gamma) - 0.032077 * Math.sin(gamma)
    - 0.014615 * Math.cos(2 * gamma) - 0.040849 * Math.sin(2 * gamma))
  const declination = 0.006918 - 0.399912 * Math.cos(gamma) + 0.070257 * Math.sin(gamma)
    - 0.006758 * Math.cos(2 * gamma) + 0.000907 * Math.sin(2 * gamma)
    - 0.002697 * Math.cos(3 * gamma) + 0.00148 * Math.sin(3 * gamma)
  const hourAngle = radians((hour * 60 + equation + 4 * longitude - 480) / 4 - 180)
  const cosine = Math.sin(radians(latitude)) * Math.sin(declination)
    + Math.cos(radians(latitude)) * Math.cos(declination) * Math.cos(hourAngle)
  return cosine > 0 ? 1098 * cosine * Math.exp(-0.059 / cosine) : 0
}

export function daylightLightComponents(weather = {}, value = null, latitude = 10.585, longitude = 122.58) {
  const condition = Object.hasOwn(DAYLIGHT_CONDITIONS, weather.daylight_condition)
    ? DAYLIGHT_CONDITIONS[weather.daylight_condition] : null
  const ghi = nonnegative(weather.shortwave_radiation_wm2)
  const dni = nonnegative(weather.direct_normal_irradiance_wm2)
  const cloud = nonnegative(weather.cloud_cover_pct)
  const reference = clearSkyShortwaveReference(value, latitude, longitude)
  const basis = ['observed', 'assumed'].includes(weather.daylight_condition_basis)
    ? weather.daylight_condition_basis : condition ? 'assumed' : null
  const result = {
    daylight_condition: condition ? weather.daylight_condition : null,
    daylight_condition_basis: basis,
    shortwave_radiation_wm2: ghi, direct_normal_irradiance_wm2: dni,
    clear_sky_shortwave_reference_wm2: reference, daylight_brightness_ratio: null,
    daylight_light_score: 0, daylight_light_status: 'unknown', daylight_light_basis: 'unknown',
    daylight_light_limiting_reason: 'daytime light unknown; cloud cover alone cannot enable activity',
    canopy_shade_enables_activity: false, light_response_is_calibrated: false,
  }
  if (condition) {
    return { ...result, daylight_light_score: condition.score,
      daylight_light_status: weather.daylight_condition, daylight_light_basis: `custom_${basis}`,
      daylight_light_limiting_reason: condition.score === 0 ? 'bright sunshine closes the daytime exception' : null }
  }
  if (ghi == null || dni == null || cloud == null || reference == null || reference <= 0) return result
  const spec = DAYLIGHT_LIGHT_SPEC
  const brightness = Math.max(ghi / reference, dni / spec.dni_reference_wm2)
  const dimness = clamp((spec.bright_brightness_ratio - brightness) / (spec.bright_brightness_ratio - spec.dim_brightness_ratio))
  const cloudStrength = clamp((cloud - spec.cloud_min_pct) / (spec.cloud_full_pct - spec.cloud_min_pct))
  const score = dimness * cloudStrength
  return { ...result, daylight_brightness_ratio: brightness,
    daylight_light_score: score, daylight_light_basis: 'radiation_estimate',
    daylight_light_status: dimness === 0 ? 'bright_sunshine' : score === 1 ? 'dim_overcast' : score > 0 ? 'intermittent_sunshine' : 'insufficient_cloud',
    daylight_light_limiting_reason: dimness === 0 ? 'strong sunlight closes the daytime exception'
      : cloudStrength === 0 ? 'insufficient cloud cover for the daytime exception' : null }
}
