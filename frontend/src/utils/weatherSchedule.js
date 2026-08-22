export const WEATHER_DEFAULTS = {
  temperature_c: 30,
  wind_speed_ms: 2,
  wind_dir_deg: 90,
  rainfall_mm: 0,
}

export const DEFAULT_GUIDED_PHASES = [
  {
    id: 'rain-buildup',
    label: 'Rain buildup',
    duration_hours: 8,
    temperature_c: 26,
    wind_speed_ms: 1.5,
    wind_dir_deg: 90,
    rainfall_mm: 2.5,
  },
  {
    id: 'drying-period',
    label: 'Drying period',
    duration_hours: 8,
    temperature_c: 28,
    wind_speed_ms: 1.5,
    wind_dir_deg: 90,
    rainfall_mm: 0,
  },
  {
    id: 'emergence-window',
    label: 'Emergence window',
    duration_hours: 8,
    temperature_c: 28,
    wind_speed_ms: 1.5,
    wind_dir_deg: 90,
    rainfall_mm: 0,
  },
]

function clone(value) {
  return JSON.parse(JSON.stringify(value))
}

export function createDefaultWeatherTimeline() {
  return {
    enabled: false,
    mode: 'advanced',
    start_datetime: localMidnightValue(),
    guided_phases: clone(DEFAULT_GUIDED_PHASES),
    advanced_blocks: buildGuidedBlocks(DEFAULT_GUIDED_PHASES, 48),
    manual_soil_context: {
      preset: 'recently_wet',
      total_rain_mm: 8,
      event_duration_hours: 4,
      hours_since_rain_ended: 6,
    },
  }
}

export function createCecidGateTestPreset(date = new Date()) {
  const dailyPattern = [
    {
      start_hour: 0,
      end_hour: 4,
      temperature_c: 26,
      wind_speed_ms: 1,
      wind_dir_deg: 90,
      rainfall_mm: 2,
    },
    {
      start_hour: 4,
      end_hour: 24,
      temperature_c: 28,
      wind_speed_ms: 1,
      wind_dir_deg: 90,
      rainfall_mm: 0,
    },
  ]

  return {
    enabled: true,
    mode: 'advanced',
    start_datetime: localMidnightValue(date),
    guided_phases: clone(DEFAULT_GUIDED_PHASES),
    advanced_blocks: repeatFirstDayBlocks(dailyPattern, 168),
    manual_soil_context: {
      preset: 'dry',
      total_rain_mm: 0,
      event_duration_hours: 1,
      hours_since_rain_ended: 0,
    },
  }
}

export function localMidnightValue(date = new Date()) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}T00:00`
}

export function localDateTimeValue(date) {
  if (!date || Number.isNaN(date.getTime())) return ''
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hour = String(date.getHours()).padStart(2, '0')
  const minute = String(date.getMinutes()).padStart(2, '0')
  return `${year}-${month}-${day}T${hour}:${minute}`
}

function finiteNumber(value, fallback) {
  const number = Number(value)
  return Number.isFinite(number) ? number : fallback
}

function normalizeWeatherValues(value = {}) {
  return {
    temperature_c: finiteNumber(value.temperature_c, WEATHER_DEFAULTS.temperature_c),
    wind_speed_ms: Math.max(0, finiteNumber(value.wind_speed_ms, WEATHER_DEFAULTS.wind_speed_ms)),
    wind_dir_deg: ((finiteNumber(value.wind_dir_deg ?? value.wind_direction_deg, WEATHER_DEFAULTS.wind_dir_deg) % 360) + 360) % 360,
    rainfall_mm: Math.max(0, finiteNumber(value.rainfall_mm, WEATHER_DEFAULTS.rainfall_mm)),
  }
}

export function buildGuidedBlocks(phases = DEFAULT_GUIDED_PHASES, hours = 48) {
  const totalHours = Math.max(1, Math.min(168, Math.floor(Number(hours) || 48)))
  const usablePhases = (Array.isArray(phases) ? phases : [])
    .map((phase) => ({
      ...phase,
      duration_hours: Math.max(1, Math.floor(finiteNumber(phase.duration_hours, 1))),
    }))
    .filter((phase) => phase.duration_hours > 0)

  if (!usablePhases.length) return []

  const blocks = []
  let cursor = 0
  let phaseIndex = 0
  while (cursor < totalHours) {
    const phase = usablePhases[phaseIndex % usablePhases.length]
    const end = Math.min(totalHours, cursor + phase.duration_hours)
    blocks.push({
      start_hour: cursor,
      end_hour: end,
      ...normalizeWeatherValues(phase),
    })
    cursor = end
    phaseIndex += 1
  }
  return blocks
}

export function normalizeAdvancedBlocks(blocks = [], hours = 48) {
  const totalHours = Math.max(1, Math.min(168, Math.floor(Number(hours) || 48)))
  return (Array.isArray(blocks) ? blocks : [])
    .map((block) => {
      const start = Math.max(0, Math.floor(finiteNumber(block.start_hour, 0)))
      const end = Math.min(totalHours, Math.floor(finiteNumber(block.end_hour, totalHours)))
      return {
        ...block,
        start_hour: start,
        end_hour: end,
        ...normalizeWeatherValues(block),
      }
    })
    .filter((block) => block.end_hour > block.start_hour)
}

export function repeatFirstDayBlocks(blocks = [], totalHours = 168) {
  const normalized = normalizeAdvancedBlocks(blocks, 24)
  if (!normalized.length) return []

  const repeated = []
  const maxHours = Math.max(24, Math.min(168, Math.floor(Number(totalHours) || 168)))
  for (let dayStart = 0; dayStart < maxHours; dayStart += 24) {
    for (const block of normalized) {
      const start = dayStart + block.start_hour
      const end = Math.min(maxHours, dayStart + block.end_hour)
      if (end <= start) continue
      repeated.push({ ...block, start_hour: start, end_hour: end })
    }
  }
  return repeated
}

export function expandWeatherBlocks(blocks = [], hours = 48, startDatetime = '') {
  const totalHours = Math.max(1, Math.min(168, Math.floor(Number(hours) || 48)))
  const expanded = Array.from({ length: totalHours }, () => ({ ...WEATHER_DEFAULTS }))
  for (const block of normalizeAdvancedBlocks(blocks, totalHours)) {
    for (let hour = block.start_hour; hour < block.end_hour; hour += 1) {
      expanded[hour] = normalizeWeatherValues(block)
    }
  }

  const startHour = parseLocalHour(startDatetime)
  return expanded.map((weather, index) => ({
    ...weather,
    hour_of_day: (startHour + index) % 24,
  }))
}

export function buildSoilRainContext(context = null, explicitPrefix = null, historyHours = 72) {
  const size = Math.max(1, Math.floor(finiteNumber(historyHours, 72)))
  if (explicitPrefix != null) {
    const values = Array.isArray(explicitPrefix) ? explicitPrefix : [explicitPrefix]
    return [...Array(size).fill(0), ...values.map((value) => Math.max(0, finiteNumber(value, 0)))].slice(-size)
  }

  const preset = context?.preset || 'dry'
  const rain = Array(size).fill(0)
  let total = 0
  let duration = 1
  let hoursSince = 0
  if (preset === 'recently_wet') {
    total = 8
    duration = 4
    hoursSince = 6
  } else if (preset === 'custom') {
    total = Math.max(0, finiteNumber(context?.total_rain_mm, 0))
    duration = Math.max(1, Math.floor(finiteNumber(context?.event_duration_hours, 1)))
    hoursSince = Math.max(0, Math.floor(finiteNumber(context?.hours_since_rain_ended, 0)))
  }
  if (total > 0 && hoursSince < size) {
    const end = size - hoursSince
    const start = Math.max(0, end - duration)
    const amount = total / Math.max(1, end - start)
    for (let index = start; index < end; index += 1) rain[index] = amount
  }
  return rain
}

function guimarasDateAt(startDatetime, hourIndex) {
  const match = String(startDatetime || '').match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2})(?::(\d{2}))?/)
  if (!match) return null
  const [, year, month, day, hour, minute = '0'] = match
  return new Date(Date.UTC(
    Number(year), Number(month) - 1, Number(day), Number(hour) - 8 + hourIndex, Number(minute),
  ))
}

function normalizeDegrees(value) {
  return ((value % 360) + 360) % 360
}

function solarUtcHour(year, month, day, latitude, longitude, sunrise) {
  const current = new Date(Date.UTC(year, month - 1, day))
  const yearStart = new Date(Date.UTC(year, 0, 0))
  const dayNumber = Math.floor((current - yearStart) / 86400000)
  const longitudeHour = longitude / 15
  const estimate = dayNumber + ((sunrise ? 6 : 18) - longitudeHour) / 24
  const meanAnomaly = 0.9856 * estimate - 3.289
  const trueLongitude = normalizeDegrees(
    meanAnomaly
      + 1.916 * Math.sin(meanAnomaly * Math.PI / 180)
      + 0.020 * Math.sin(2 * meanAnomaly * Math.PI / 180)
      + 282.634,
  )
  let rightAscension = normalizeDegrees(
    Math.atan(0.91764 * Math.tan(trueLongitude * Math.PI / 180)) * 180 / Math.PI,
  )
  rightAscension += Math.floor(trueLongitude / 90) * 90 - Math.floor(rightAscension / 90) * 90
  rightAscension /= 15
  const sinDeclination = 0.39782 * Math.sin(trueLongitude * Math.PI / 180)
  const cosDeclination = Math.cos(Math.asin(sinDeclination))
  const cosHour = (
    Math.cos(90.833 * Math.PI / 180)
      - sinDeclination * Math.sin(latitude * Math.PI / 180)
  ) / (cosDeclination * Math.cos(latitude * Math.PI / 180))
  if (cosHour < -1 || cosHour > 1) return sunrise ? 22 : 10
  let hourAngle = Math.acos(cosHour) * 180 / Math.PI
  if (sunrise) hourAngle = 360 - hourAngle
  hourAngle /= 15
  return normalizeDegrees((hourAngle + rightAscension - 0.06571 * estimate - 6.622 - longitudeHour) * 15) / 15
}

export function solarTimesForGuimaras(value, latitude = 10.585, longitude = 122.58) {
  if (!(value instanceof Date) || Number.isNaN(value.getTime())) return null
  const local = new Date(value.getTime() + 8 * 3600000)
  const year = local.getUTCFullYear()
  const month = local.getUTCMonth() + 1
  const day = local.getUTCDate()
  const sunriseLocalHour = (solarUtcHour(year, month, day, latitude, longitude, true) + 8) % 24
  const sunsetLocalHour = (solarUtcHour(year, month, day, latitude, longitude, false) + 8) % 24
  const localMidnightUtc = Date.UTC(year, month - 1, day, -8)
  return {
    sunrise: new Date(localMidnightUtc + sunriseLocalHour * 3600000),
    sunset: new Date(localMidnightUtc + sunsetLocalHour * 3600000),
  }
}

function soilWetness(rainHistory) {
  const decay = 2 ** (-1 / 48)
  return rainHistory.reduce((wetness, rainfall) => wetness * decay + Math.max(0, rainfall), 0)
}

export function summarizeWeatherBlocks(blocks = [], hours = 48, startDatetime = '', threshold = 5, options = {}) {
  const expanded = expandWeatherBlocks(blocks, hours, startDatetime)
  const rainHistory = buildSoilRainContext(
    options.manual_soil_context,
    options.manual_weather_prefix_rain,
    72,
  )
  let maxRain24h = 0
  let maxWetness = soilWetness(rainHistory)
  let hasDryCrepuscularWindow = false
  let hasCalmCrepuscularWindow = false
  let hasCalmHour = false
  let coveredHours = 0
  let favorableHours = 0
  let limitedHours = 0
  let closedHours = 0
  const preview = []

  const normalized = normalizeAdvancedBlocks(blocks, hours)
    .sort((left, right) => left.start_hour - right.start_hour)
  let coverageStart = null
  let coverageEnd = null
  for (const block of normalized) {
    if (coverageStart == null) {
      coverageStart = block.start_hour
      coverageEnd = block.end_hour
    } else if (block.start_hour <= coverageEnd) {
      coverageEnd = Math.max(coverageEnd, block.end_hour)
    } else {
      coveredHours += coverageEnd - coverageStart
      coverageStart = block.start_hour
      coverageEnd = block.end_hour
    }
  }
  if (coverageStart != null) coveredHours += coverageEnd - coverageStart

  for (let index = 0; index < expanded.length; index += 1) {
    const entry = expanded[index]
    rainHistory.push(entry.rainfall_mm)
    if (rainHistory.length > 72) rainHistory.shift()
    const rain24h = rainHistory.slice(-24).reduce((sum, value) => sum + value, 0)
    maxRain24h = Math.max(maxRain24h, rain24h)
    const wetness = soilWetness(rainHistory)
    maxWetness = Math.max(maxWetness, wetness)
    const moistureScore = Math.min(1, wetness / Math.max(threshold, Number.EPSILON))
    const dryingScore = entry.rainfall_mm <= 0.1
      ? 1
      : entry.rainfall_mm >= 1 ? 0 : (1 - entry.rainfall_mm) / 0.9
    const windScore = Math.exp(-((entry.wind_speed_ms / 4) ** 2))
    const suitability = moistureScore * dryingScore * windScore

    const currentDate = guimarasDateAt(startDatetime, index)
    const solar = solarTimesForGuimaras(
      currentDate,
      finiteNumber(options.latitude, 10.585),
      finiteNumber(options.longitude, 122.58),
    )
    const crepuscular = solar
      ? Math.min(Math.abs(currentDate - solar.sunrise), Math.abs(currentDate - solar.sunset)) <= 3600000
      : (entry.hour_of_day >= 5 && entry.hour_of_day < 7) || (entry.hour_of_day >= 17 && entry.hour_of_day < 19)
    const status = !crepuscular ? 'closed' : suitability >= 0.25 ? 'favorable' : 'limited'
    if (status === 'favorable') favorableHours += 1
    else if (status === 'limited') limitedHours += 1
    else closedHours += 1

    if (entry.wind_speed_ms <= 3) hasCalmHour = true
    if (crepuscular && entry.rainfall_mm <= 0.1) {
      hasDryCrepuscularWindow = true
      if (entry.wind_speed_ms <= 3) hasCalmCrepuscularWindow = true
    }
    preview.push({
      step: index,
      hour_of_day: entry.hour_of_day,
      status,
      suitability_score: suitability,
      soil_wetness_mm: wetness,
      moisture_score: moistureScore,
      drying_score: dryingScore,
      wind_score: windScore,
    })
  }

  return {
    hours: expanded.length,
    max_rain_24h: maxRain24h,
    max_soil_wetness_mm: maxWetness,
    covered_hours: Math.min(hours, coveredHours),
    has_dry_crepuscular_window: hasDryCrepuscularWindow,
    has_calm_crepuscular_window: hasCalmCrepuscularWindow,
    has_calm_hour: hasCalmHour,
    reaches_rain_threshold: maxWetness >= threshold,
    favorable_hours: favorableHours,
    limited_hours: limitedHours,
    closed_hours: closedHours,
    preview,
  }
}

function parseLocalHour(value) {
  if (typeof value !== 'string') return 0
  const match = value.match(/T(\d{2})/) || value.match(/^(\d{1,2})/)
  const hour = match ? Number(match[1]) : 0
  return Number.isFinite(hour) ? Math.max(0, Math.min(23, hour)) : 0
}
