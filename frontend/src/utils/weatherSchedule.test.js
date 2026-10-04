import test from 'node:test'
import assert from 'node:assert/strict'
import {
  buildGuidedBlocks,
  buildSoilRainContext,
  cecidWindActivity,
  cecidWindDirectionAssist,
  cecidWindSurvival,
  createCecidGateTestPreset,
  solarTimesForGuimaras,
  summarizeWeatherBlocks,
  repeatFirstDayBlocks,
  addCustomWeatherPeriod,
  createConstantWeatherTimeline,
  createDefaultWeatherTimeline,
  customWeatherBlocks,
  customWeatherRequestFields,
  expandWeatherBlocks,
  restoreCustomWeatherTimeline,
  weatherCoverage,
} from './weatherSchedule.js'

test('guided schedules repeat wet and dry phases across the simulation', () => {
  const phases = [
    { duration_hours: 8, temperature_c: 26, wind_speed_ms: 1.5, wind_dir_deg: 90, rainfall_mm: 2.5 },
    { duration_hours: 16, temperature_c: 28, wind_speed_ms: 1.5, wind_dir_deg: 90, rainfall_mm: 0 },
  ]
  const blocks = buildGuidedBlocks(phases, 72)

  assert.equal(blocks.at(-1).end_hour, 72)
  assert.equal(blocks.filter((block) => block.rainfall_mm > 0).length, 3)
  assert.equal(blocks[2].start_hour, 24)
  assert.equal(blocks[4].start_hour, 48)
})

test('a new custom scenario has one dry period that follows the run duration', () => {
  const timeline = createDefaultWeatherTimeline()
  assert.equal(timeline.advanced_blocks.length, 1)
  assert.equal(timeline.manual_soil_context.preset, 'dry')
  for (const hours of [24, 48, 72, 168]) {
    assert.deepEqual(customWeatherBlocks(timeline, hours).map((block) => [block.start_hour, block.end_hour]), [[0, hours]])
  }
})

test('constant Fruit Fly custom weather preserves the legacy request values and local start', () => {
  const params = {
    hours: 168,
    manual_weather: { temperature_c: 33.2, wind_speed_ms: 1.4, wind_dir_deg: 315, rainfall_mm: 0.3 },
    manual_weather_start: '2026-10-04T06:00:00+08:00',
  }
  const restored = restoreCustomWeatherTimeline(params)
  assert.deepEqual(customWeatherRequestFields(restored, params.hours, 'fruitfly'), {
    manual_weather: params.manual_weather,
    manual_weather_start: params.manual_weather_start,
  })
  assert.equal(customWeatherRequestFields(restored, 24, 'fruitfly').manual_weather_blocks, undefined)
})

test('adding a period preserves the existing hourly conditions', () => {
  const timeline = createConstantWeatherTimeline({ temperature_c: 31, wind_speed_ms: 1, rainfall_mm: 3 }, 72)
  const split = addCustomWeatherPeriod(timeline, 72)
  assert.equal(split.coverage_mode, 'scheduled')
  assert.deepEqual(split.advanced_blocks.map((block) => [block.start_hour, block.end_hour]), [[0, 8], [8, 72]])
  assert.deepEqual(expandWeatherBlocks(customWeatherBlocks(split, 72), 72),
    expandWeatherBlocks(customWeatherBlocks(timeline, 72), 72))
})

test('explicitly scheduled periods keep their boundaries and expose missing or overlapping hours', () => {
  const timeline = {
    mode: 'advanced', coverage_mode: 'scheduled',
    advanced_blocks: [{ start_hour: 0, end_hour: 24, rainfall_mm: 8 }],
  }
  assert.equal(customWeatherBlocks(timeline, 168)[0].end_hour, 24)
  assert.deepEqual(weatherCoverage(timeline.advanced_blocks, 168), { uncovered_hours: 144, overlapping_hours: 0 })
  assert.deepEqual(weatherCoverage([
    { start_hour: 0, end_hour: 12 }, { start_hour: 8, end_hour: 24 },
  ], 24), { uncovered_hours: 0, overlapping_hours: 4 })
  assert.throws(() => customWeatherRequestFields({ advanced_blocks: [] }, 48, 'fruitfly'), /Add a weather period/)
})

test('old multi-period Cecid scenarios preserve rain, start time, and soil history', () => {
  const params = {
    hours: 48,
    manual_weather_start: '2026-04-01T00:00:00+08:00',
    manual_weather_blocks: [
      { start_hour: 0, end_hour: 4, temperature_c: 26, wind_speed_ms: 1, wind_dir_deg: 90, rainfall_mm: 2 },
      { start_hour: 4, end_hour: 48, temperature_c: 28, wind_speed_ms: 1, wind_dir_deg: 90, rainfall_mm: 0 },
    ],
    manual_soil_context: { preset: 'recently_wet' },
  }
  const timeline = restoreCustomWeatherTimeline(params)
  assert.equal(timeline.coverage_mode, 'scheduled')
  assert.deepEqual(customWeatherRequestFields(timeline, 48, 'cecid'), {
    manual_weather_blocks: params.manual_weather_blocks,
    manual_weather_start: params.manual_weather_start,
    manual_soil_context: params.manual_soil_context,
  })
  assert.equal(customWeatherRequestFields(timeline, 48, 'fruitfly').manual_soil_context, undefined)
  assert.equal(restoreCustomWeatherTimeline({ hours: 48 }), null)
})

test('saved hourly series retain inherited values, nulls, precedence and repeated tail', () => {
  const params = {
    hours: 5,
    manual_weather_start: '2026-10-04T05:00:00+08:00',
    manual_weather_series: [
      { temperature_c: 27, wind_speed_ms: 1, rainfall_mm: 2 },
      { temperature_c: null, rainfall_mm: 0 },
      { wind_speed_ms: 3 },
    ],
    manual_weather_blocks: [{ start_hour: 0, end_hour: 5, temperature_c: 40 }],
  }
  const timeline = restoreCustomWeatherTimeline(params)
  const entries = expandWeatherBlocks(customWeatherBlocks(timeline, 5), 5)
  assert.deepEqual(entries.map(({ temperature_c, wind_speed_ms, rainfall_mm }) => [temperature_c, wind_speed_ms, rainfall_mm]),
    [[27, 1, 2], [27, 1, 0], [27, 3, 0], [27, 3, 0], [27, 3, 0]])
  assert.equal(timeline.start_datetime, params.manual_weather_start)
})

test('saved requests take precedence over stale editor values without extending explicit periods', () => {
  const stale = createConstantWeatherTimeline({ temperature_c: 40, rainfall_mm: 20 }, 48)
  const recorded = { temperature_c: 27, wind_speed_ms: 1, wind_dir_deg: 90, rainfall_mm: 0 }
  const params = { hours: 48, dashboard_state: { weather_timeline: stale } }
  const blocks = [{ ...recorded, start_hour: 0, end_hour: 24 }]
  const schedule = restoreCustomWeatherTimeline({ ...params, manual_weather_blocks: blocks })
  assert.equal(schedule.coverage_mode, 'scheduled')
  assert.deepEqual(customWeatherRequestFields(schedule, 48, 'fruitfly'), { manual_weather_blocks: blocks })
  const constant = restoreCustomWeatherTimeline({ ...params, manual_weather: recorded })
  assert.deepEqual(customWeatherRequestFields(constant, 48, 'fruitfly'), { manual_weather: recorded })
})

test('summary uses the local wall-clock start hour for dawn and dusk', () => {
  const blocks = buildGuidedBlocks([
    { duration_hours: 8, temperature_c: 26, wind_speed_ms: 1.5, rainfall_mm: 2.5 },
    { duration_hours: 16, temperature_c: 28, wind_speed_ms: 1.5, rainfall_mm: 0 },
  ], 24)
  const summary = summarizeWeatherBlocks(blocks, 24, '2026-04-01T05:00', 5)

  assert.equal(summary.reaches_rain_threshold, true)
  assert.equal(summary.has_dry_crepuscular_window, true)
  assert.equal(summary.has_calm_crepuscular_window, true)
})

test('advanced daily patterns can be repeated and remain bounded', () => {
  const repeated = repeatFirstDayBlocks([
    { start_hour: 0, end_hour: 6, rainfall_mm: 3, temperature_c: 26, wind_speed_ms: 2, wind_dir_deg: 90 },
    { start_hour: 6, end_hour: 24, rainfall_mm: 0, temperature_c: 28, wind_speed_ms: 2, wind_dir_deg: 90 },
  ], 72)

  assert.equal(repeated.length, 6)
  assert.deepEqual(repeated.slice(-2).map((block) => [block.start_hour, block.end_hour]), [[48, 54], [54, 72]])
})

test('summary reports uncovered hours once when blocks overlap', () => {
  const summary = summarizeWeatherBlocks([
    { start_hour: 0, end_hour: 6, rainfall_mm: 1 },
    { start_hour: 2, end_hour: 8, rainfall_mm: 0 },
  ], 12, '2026-04-01T00:00', 5)

  assert.equal(summary.covered_hours, 8)
  assert.equal(summary.hours, 12)
})

test('soil selector matches the backend 72-hour recently-wet preset', () => {
  const rain = buildSoilRainContext({ preset: 'recently_wet' })
  assert.equal(rain.length, 72)
  assert.equal(rain.reduce((sum, value) => sum + value, 0), 8)
  assert.deepEqual(rain.slice(-10, -6), [2, 2, 2, 2])
  assert.deepEqual(rain.slice(-6), [0, 0, 0, 0, 0, 0])

  const explicit = buildSoilRainContext({ preset: 'recently_wet' }, [1, 2])
  assert.deepEqual(explicit.slice(-2), [1, 2])
  assert.equal(explicit.reduce((sum, value) => sum + value, 0), 3)
})

test('solar preview and suitability match Guimaras backend assumptions', () => {
  const localNoon = new Date('2026-04-01T04:00:00Z')
  const solar = solarTimesForGuimaras(localNoon, 10.585, 122.58)
  const sunriseHour = (solar.sunrise.getUTCHours() + 8) % 24 + solar.sunrise.getUTCMinutes() / 60
  const sunsetHour = (solar.sunset.getUTCHours() + 8) % 24 + solar.sunset.getUTCMinutes() / 60
  assert.ok(Math.abs(sunriseHour - 5.78) < 0.08)
  assert.ok(Math.abs(sunsetHour - 18.0) < 0.08)

  const summary = summarizeWeatherBlocks([
    { start_hour: 0, end_hour: 1, rainfall_mm: 0, temperature_c: 28, wind_speed_ms: 1, wind_dir_deg: 90 },
  ], 1, '2026-04-01T18:00', 5, {
    manual_soil_context: { preset: 'recently_wet' },
    latitude: 10.585,
    longitude: 122.58,
  })
  assert.equal(summary.preview[0].status, 'favorable')
  assert.equal(summary.preview[0].suitability_score, 1)
})

test('Cecid wind activity mirrors the backend soft inverse-square curve', () => {
  assert.equal(cecidWindActivity(0), 1)
  assert.equal(cecidWindActivity(1), 1)
  assert.equal(cecidWindActivity(5 / 3.6), 1)
  const expectedAtThreeMs = 1 / (1 + ((((3 * 3.6) - 5) / 6) ** 2))
  assert.ok(Math.abs(cecidWindActivity(3) - expectedAtThreeMs) < 1e-12)
  assert.ok(cecidWindActivity(3) > 0.5)
  assert.equal(cecidWindSurvival(3), cecidWindActivity(3))
  assert.equal(cecidWindDirectionAssist(3.2 / 3.6), 0)
  assert.ok(cecidWindDirectionAssist(3) > 0.2)
  assert.equal(cecidWindDirectionAssist(15 / 3.6), 0.35)
})

test('Cecid gate test preset creates favorable dawn and dusk windows', () => {
  const preset = createCecidGateTestPreset(new Date(2026, 3, 1, 12, 0))
  const summary = summarizeWeatherBlocks(
    preset.advanced_blocks,
    48,
    preset.start_datetime,
    5,
    { manual_soil_context: preset.manual_soil_context },
  )
  const favorableHours = new Set(
    summary.preview
      .filter((entry) => entry.status === 'favorable')
      .map((entry) => entry.hour_of_day),
  )

  assert.equal(preset.start_datetime, '2026-04-01T00:00')
  assert.equal(preset.manual_soil_context.preset, 'dry')
  assert.equal('simulation_random_seed' in preset, false)
  assert.equal('cecid_assumed_source_count' in preset, false)
  assert.equal(Object.keys(preset).some((key) => key.startsWith('simulation_')), false)
  assert.deepEqual(
    preset.advanced_blocks.slice(0, 4).map((block) => [block.start_hour, block.end_hour, block.rainfall_mm]),
    [[0, 4, 2], [4, 24, 0], [24, 28, 2], [28, 48, 0]],
  )
  assert.equal(summary.reaches_rain_threshold, true)
  assert.equal(summary.has_dry_crepuscular_window, true)
  assert.ok([...favorableHours].some((hour) => hour >= 5 && hour <= 7))
  assert.ok([...favorableHours].some((hour) => hour >= 17 && hour <= 19))
})
