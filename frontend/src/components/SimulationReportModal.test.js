import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

const require = createRequire(import.meta.url)
const bundled = await build({
  entryPoints: [fileURLToPath(new URL('./SimulationReportModal.jsx', import.meta.url))],
  bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic',
  external: ['react', 'react/jsx-runtime', 'react-dom'],
  plugins: [{ name: 'replace-webgl-map-for-report-tests', setup(builder) {
    builder.onResolve({ filter: /^\.\/RiskMap$/ }, () => ({ path: 'RiskMap', namespace: 'report-test-map' }))
    builder.onLoad({ filter: /.*/, namespace: 'report-test-map' }, () => ({
      contents: "import { forwardRef } from 'react'; export default forwardRef(() => null)", loader: 'js',
    }))
  } }],
})
const componentModule = { exports: {} }
new Function('require', 'module', 'exports', bundled.outputFiles[0].text)(require, componentModule, componentModule.exports)
const { default: SimulationReportModal, ReportRecordFields, handleReportTabKey } = componentModule.exports
const details = { reference: '', preparedBy: '', organization: '', reviewedBy: '', fieldNotes: '', plannedActions: '' }

function elements(tree) {
  if (Array.isArray(tree)) return tree.flatMap(elements)
  if (!tree || typeof tree !== 'object') return []
  return [tree, ...elements(tree.props?.children)]
}

test('report record fields are bounded, labeled, multiline and disabled during export', () => {
  const html = renderToStaticMarkup(React.createElement(ReportRecordFields, {
    recordDetails: { ...details, preparedBy: '<reviewer>', fieldNotes: 'First line\nSecond line' },
    onChange() {}, disabled: true,
  }))
  for (const name of Object.keys(details)) {
    assert.match(html, new RegExp(`for="report-${name}"`))
    assert.match(html, new RegExp(`id="report-${name}"`))
  }
  assert.match(html, /value="&lt;reviewer&gt;"/)
  assert.match(html, /First line\nSecond line/)
  assert.match(html, /name="reference"[^>]*maxLength="120"/i)
  assert.match(html, /name="fieldNotes"[^>]*maxLength="3000"/i)
  assert.equal((html.match(/ disabled=""/g) || []).length, 6)
})

test('input changes bound pasted values and preserve the other record fields', () => {
  let state = { ...details, organization: 'Orchard office' }
  const controls = elements(ReportRecordFields({ recordDetails: state,
    onChange: (update) => { state = update(state) },
  })).filter((element) => ['input', 'textarea'].includes(element.type))
  controls.find((control) => control.props.name === 'reference').props.onChange({ target: { value: 'A'.repeat(200) } })
  controls.find((control) => control.props.name === 'fieldNotes').props.onChange({ target: { value: 'Tree checked\nNext visit' } })
  assert.equal(state.reference.length, 120)
  assert.equal(state.fieldNotes, 'Tree checked\nNext visit')
  assert.equal(state.organization, 'Orchard office')
})

test('keyboard focus wraps across visible text fields and excludes hidden controls', () => {
  let focused, prevented = 0
  const input = { offsetParent: {}, focus: () => { focused = 'input' } }
  const hidden = { offsetParent: null, focus: () => { focused = 'hidden' } }
  const textarea = { offsetParent: {}, focus: () => { focused = 'textarea' } }
  const dialog = { querySelectorAll: (selector) => {
    assert.match(selector, /input:not\(\[disabled\]\)/)
    assert.match(selector, /textarea:not\(\[disabled\]\)/)
    return [input, textarea, hidden]
  } }
  const event = { key: 'Tab', shiftKey: false, preventDefault: () => { prevented += 1 } }
  handleReportTabKey(event, dialog, textarea)
  assert.equal(focused, 'input')
  handleReportTabKey({ ...event, shiftKey: true }, dialog, input)
  assert.equal(focused, 'textarea')
  assert.equal(prevented, 2)
})

test('preview labels portrait export and distinguishes frequency from one-run totals', () => {
  const html = renderToStaticMarkup(React.createElement(SimulationReportModal, {
    onClose() {}, run: { pest_type: 'fruitfly', hours: 48, n_infested_final: 1,
      risk_geojson: { type: 'FeatureCollection', features: [{ type: 'Feature',
        geometry: { type: 'Point', coordinates: [122, 10] }, properties: {
          tree_id: '1', state: 'infested', risk: 1, ensemble_runs: 5,
          ensemble_infestation_count: 2, ensemble_infestation_frequency: 0.4,
        } }] },
      request_payload: { impact_assumptions: { yield_per_tree_kg: 45,
        farmgate_price_php_per_kg: 60, damage_base: 30 } },
    },
  }))
  assert.match(html, /A4 portrait/)
  assert.match(html, /Maximum map frequency: 40\.0%/)
  assert.match(html, /Infested cells in one run: 1/)
  assert.doesNotMatch(html, /A4 landscape|Potential savings with recommendations/)
  assert.match(html, /Record details/)
  assert.match(html, /Planned actions \/ follow-up/)
})
