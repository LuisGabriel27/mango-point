import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createConstantWeatherTimeline } from '../../utils/weatherSchedule.js'

const require = createRequire(import.meta.url)
async function componentExports(relativePath) {
  const result = await build({
    entryPoints: [fileURLToPath(new URL(relativePath, import.meta.url))],
    bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic',
    external: ['react', 'react/jsx-runtime', 'react-dom', 'react-datepicker'],
    plugins: [{
      name: 'omit-styles-in-server-render-tests',
      setup(builder) {
        builder.onResolve({ filter: /\.css$/ }, (args) => ({ path: args.path, namespace: 'test-style' }))
        builder.onLoad({ filter: /.*/, namespace: 'test-style' }, () => ({ contents: '', loader: 'js' }))
      },
    }],
  })
  const module = { exports: {} }
  // Match Vite's default-import interop for the datepicker's CommonJS export.
  const componentRequire = (id) => {
    const dependency = require(id)
    return id === 'react-datepicker' ? dependency.default ?? dependency : dependency
  }
  new Function('require', 'module', 'exports', result.outputFiles[0].text)(componentRequire, module, module.exports)
  return module.exports
}
const { default: WeatherCard, CustomWeatherEditor, DaylightConditionField } = await componentExports('./WeatherCard.jsx')
const { default: OverviewTab } = await componentExports('../tabs/OverviewTab.jsx')
const timeline = createConstantWeatherTimeline({ temperature_c: 27, rainfall_mm: 0, wind_speed_ms: 1 }, 48)

test('the weather selector has two choices and the editor exposes exact values plus shortcuts', () => {
  const html = renderToStaticMarkup(React.createElement(WeatherCard, {
    weatherOverrideActive: true, weatherTimeline: timeline, simulationHours: 48, embedded: true,
  }))
  assert.match(html, />Live Forecast<\/button>/)
  assert.match(html, />Custom Weather<\/button>/)
  assert.doesNotMatch(html, /Weather timeline|Cecid weather timeline/)
  /* The detailed value shortcuts now live in the weather-period modal.
  assert.match(html, /Entire simulation/)
  assert.match(html, /Hour 0–48/)
  assert.match(html, /aria-label="Warm: 27 °C"/)
  assert.match(html, /aria-label="None: 0 mm\/h"/)
  assert.match(html, /aria-label="Calm: 1 m\/s"/)
  assert.equal((html.match(/type="number"/g) || []).length, 0)
  */
  assert.match(html, /Edit periods/)
  assert.match(html, /Schedule ready to review/)
  assert.match(html, /Soil &amp; Cecid test preset/)
})

test('Cecid soil settings are discoverable before selecting Cecid in simulation controls', () => {
  const render = (pestType) => renderToStaticMarkup(React.createElement(CustomWeatherEditor, {
    timeline, hours: 72, pestType, onChange() {},
  }))
  const fruitfly = render('fruitfly')
  const cecid = render('cecid')
  assert.match(fruitfly, /Soil &amp; Cecid test preset/)
  assert.match(fruitfly, /Available for Cecid Fly/)
  assert.match(fruitfly, /Dawn \+ dusk test/)
  assert.match(cecid, /<details class="weather-cecid-settings">/)
  assert.match(cecid, /Starting soil condition/)
  assert.match(cecid, /Dawn \+ dusk test/)
  assert.match(cecid, /Hour 0–72/)
})

test('an empty saved schedule is visibly incomplete rather than showing unsaved default values', () => {
  const html = renderToStaticMarkup(React.createElement(WeatherCard, {
    weatherOverrideActive: true, weatherTimeline: { ...timeline, advanced_blocks: [] },
    simulationHours: 48, embedded: true,
  }))
  assert.match(html, /48 hour\(s\) are uncovered/)
  assert.equal((html.match(/type="number"/g) || []).length, 0)
  assert.match(html, /No weather periods configured/)
})

test('soil controls expose moist now as a labeled scenario rather than invented rainfall', () => {
  const html = renderToStaticMarkup(React.createElement(CustomWeatherEditor, {
    timeline: { ...timeline, manual_soil_context: { preset: 'moist', initial_moisture_score: 0.8 } },
    hours: 48, pestType: 'cecid', onChange() {},
  }))
  assert.match(html, /Moist now/)
  assert.match(html, /Moist at Hour 0/)
  assert.match(html, /Moisture strength/)
  assert.match(html, /value="80"/)
  assert.match(html, /without adding earlier rain/)
  assert.match(html, /not a measured soil-water percentage/)
})

test('Overview emphasizes infestation and no longer labels the maximum score as critical risk', () => {
  const html = renderToStaticMarkup(React.createElement(OverviewTab, {
    totalTrees: 194, simData: { n_infested_final: 39, peak_risk: 1, hours: 168 },
  }))
  assert.match(html, /Infestation rate/)
  assert.match(html, /20\.1%/)
  assert.match(html, /39 of 194 trees/)
  assert.doesNotMatch(html, /Peak risk score|Critical/)
})

test('custom daylight controls separate outdoor light and evidence from cloud cover and canopy shade', () => {
  const html = renderToStaticMarkup(React.createElement(DaylightConditionField, {
    block: { cloud_cover_pct: 100, daylight_condition: 'bright_sunshine', daylight_condition_basis: 'observed' }, onChange() {},
  }))
  assert.match(html, /Daylight light condition/)
  assert.match(html, /Bright sunshine/)
  assert.match(html, /Intermittent sunshine/)
  assert.match(html, /Dim overcast/)
  assert.match(html, /value="bright_sunshine" selected=""/)
  assert.match(html, /value="observed" selected=""/)
  assert.match(html, /Assumed scenario/)
  assert.match(html, /Tree-canopy shade alone does not enable Cecid emergence or movement/)
})

test('live weather displays zero radiation and leaves missing sunlight unavailable', () => {
  const render = (current) => renderToStaticMarkup(React.createElement(WeatherCard, {
    weather: { current: { temperature_c: 28, humidity: 70, wind_speed_ms: 1, source: 'open-meteo', ...current } }, embedded: true,
  }))
  const zero = render({ shortwave_radiation_wm2: 0, direct_normal_irradiance_wm2: 0 })
  assert.match(zero, /Solar: 0 W\/m²/)
  assert.match(zero, /Direct sunlight: 0 W\/m²/)
  assert.match(render({}), /Solar: Unavailable/)
})
