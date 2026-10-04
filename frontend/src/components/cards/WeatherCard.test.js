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
const { default: WeatherCard, CustomWeatherEditor } = await componentExports('./WeatherCard.jsx')
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

test('Overview emphasizes infestation and no longer labels the maximum score as critical risk', () => {
  const html = renderToStaticMarkup(React.createElement(OverviewTab, {
    totalTrees: 194, simData: { n_infested_final: 39, peak_risk: 1, hours: 168 },
  }))
  assert.match(html, /Infestation rate/)
  assert.match(html, /20\.1%/)
  assert.match(html, /39 of 194 trees/)
  assert.doesNotMatch(html, /Peak risk score|Critical/)
})
