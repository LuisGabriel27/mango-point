import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

const require = createRequire(import.meta.url)
async function component(path, plugins = []) {
  const bundle = await build({ entryPoints: [fileURLToPath(new URL(path, import.meta.url))],
    bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic',
    external: ['react', 'react/jsx-runtime'], plugins })
  const module = { exports: {} }
  new Function('require', 'module', 'exports', bundle.outputFiles[0].text)(require, module, module.exports)
  return module.exports.default
}
const SourcePresenceControl = await component('./SourcePresenceControl.jsx')
const TreeStatusSelect = await component('./TreeStatusSelect.jsx')
const Sidebar = await component('./Sidebar.jsx', [{ name: 'capture-simulation-inputs', setup(builder) {
  builder.onResolve({ filter: /^\.\/cards\// }, args => ({ path: args.path, namespace: 'test-card' }))
  builder.onLoad({ filter: /.*/, namespace: 'test-card' }, args => ({ loader: 'jsx',
    contents: args.path.endsWith('SimulationCard')
      ? 'export default function Card(props) { return <output>{JSON.stringify({resolved:props.treeSourceProbabilityOverrides,individual:props.individualSourceProbabilityOverrides})}</output> }'
      : 'export default function Card() { return null }',
  }))
} }])
const render = (Component, props) => renderToStaticMarkup(React.createElement(Component, props))

test('confirmed infected sources display 100% without an adjustable probability', () => {
  const html = render(SourcePresenceControl, { status: 'infected', value: 0.2 })
  assert.match(html, /100% \(confirmed\)/)
  assert.doesNotMatch(html, /<input|<select/)
})

test('uncertain status controls support default, custom and endpoint percentages', () => {
  for (const status of ['history_infected', 'suspect']) {
    const fallback = render(SourcePresenceControl, { status, value: null })
    assert.match(fallback, /value="default" selected=""/)
    assert.doesNotMatch(fallback, /type="range"/)
    for (const value of [0, 0.7, 1]) {
      const html = render(SourcePresenceControl, { status, value })
      assert.match(html, /value="custom" selected=""/)
      assert.match(html, new RegExp(`value="${value * 100}"`))
      assert.match(html, /for="[^"]+-probability"/)
    }
  }
})

test('Healthy, Bagged and Dead do not offer source-presence controls', () => {
  for (const status of ['healthy', 'bagged', 'dead']) assert.equal(render(SourcePresenceControl, { status }), '')
})

test('individual tree editor restores a percentage and its status together', () => {
  const html = render(TreeStatusSelect, { defaultValue: 'history_infected', defaultSourceProbability: 0.7 })
  assert.match(html, /value="history_infected" selected=""/)
  assert.match(html, /value="70"/)
  assert.match(html, /Apply Changes/)
})

test('sidebar forwards resolved probabilities and explicit default choices to the simulation card', () => {
  const resolved = { a: 0, b: 1, c: 0.7 }
  const individual = { a: null, c: 0.3 }
  const html = render(Sidebar, { orchards: [], playbackFrames: [], activeWorkflow: 'simulate',
    treeSourceProbabilityOverrides: resolved, individualSourceProbabilityOverrides: individual })
  const encoded = html.match(/<output>(.*?)<\/output>/)[1].replaceAll('&quot;', '"')
  assert.deepEqual(JSON.parse(encoded), { resolved, individual })
})
