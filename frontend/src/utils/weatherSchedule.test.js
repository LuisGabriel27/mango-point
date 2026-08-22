import test from 'node:test'
import assert from 'node:assert/strict'
import {
  buildGuidedBlocks,
  buildSoilRainContext,
  createCecidGateTestPreset,
  solarTimesForGuimaras,
  summarizeWeatherBlocks,
  repeatFirstDayBlocks,
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
  assert.ok(Math.abs(summary.preview[0].suitability_score - Math.exp(-((1 / 4) ** 2))) < 1e-9)
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
  assert.deepEqual(
    preset.advanced_blocks.slice(0, 4).map((block) => [block.start_hour, block.end_hour, block.rainfall_mm]),
    [[0, 4, 2], [4, 24, 0], [24, 28, 2], [28, 48, 0]],
  )
  assert.equal(summary.reaches_rain_threshold, true)
  assert.equal(summary.has_dry_crepuscular_window, true)
  assert.ok([...favorableHours].some((hour) => hour >= 5 && hour <= 7))
  assert.ok([...favorableHours].some((hour) => hour >= 17 && hour <= 19))
})
