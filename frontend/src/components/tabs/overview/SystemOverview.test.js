import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { overviewDateKey } from '../../../utils/systemOverview.js'

const require = createRequire(import.meta.url)
async function component(path, plugins) {
  const bundle = await build({ entryPoints: [fileURLToPath(new URL(path, import.meta.url))],
    bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic',
    external: ['react', 'react/jsx-runtime'], plugins })
  const module = { exports: {} }
  new Function('require', 'module', 'exports', bundle.outputFiles[0].text)(require, module, module.exports)
  return module.exports.default
}
const SystemOverview = await component('./SystemOverview.jsx', [{ name: 'overview-chart-test', setup(builder) {
  builder.onResolve({ filter: /^\.\/OverviewActivityChart$/ }, () => ({ path: 'chart', namespace: 'chart-test' }))
  builder.onLoad({ filter: /.*/, namespace: 'chart-test' }, () => ({ loader: 'jsx',
    contents: 'export default function Chart() { return <div aria-label="Activity chart" /> }' }))
} }])
const Chart = await component('./OverviewActivityChart.jsx', [{ name: 'capture-chart-data', setup(builder) {
  builder.onResolve({ filter: /^(react-plotly.js\/factory|plotly.js-dist-min)$/ },
    (args) => ({ path: args.path, namespace: 'plot-test' }))
  builder.onLoad({ filter: /.*/, namespace: 'plot-test' }, (args) => ({ loader: 'jsx',
    contents: args.path === 'react-plotly.js/factory'
      ? 'export default function factory() { return function Plot(props) { return <output>{JSON.stringify({ data: props.data, layout: props.layout })}</output> } }'
      : 'export default {}',
  }))
} }])

const props = { period: 'week', selectedDate: '2024-02-29', orchardId: '', directory: [], loading: false,
  onPeriodChange() {}, onDateChange() {}, onOrchardChange() {}, onRefresh() {} }
const data = {
  start_at: '2026-10-03T16:00:00Z', end_at: '2026-10-10T00:00:00Z', computed_at: '2026-10-10T00:00:00Z',
  current_model_version: 'v17', inventory: { orchards: 2, monitored_orchards: 1, trees: 125 },
  simulations: { total: 5, completed: 5, failed: 0, other: 0 },
  observations: { total: 7, inspected: 6, present: 2, absent: 4, not_inspected: 1 },
  alerts: { raised: 3, active: 8, high_critical_active: 2 }, timeline: [],
  orchard_activity: [{ orchard_id: 'a', name: '<Orchard A>', tree_count: 125, simulations: 5,
    observations: 6, present: 2, alerts: 3, active_alerts: 8 }],
  pests: [{ pest_type: 'cecid', simulations: 5, observations: 6, present: 2 }],
  engines: { grid: 3, tree_graph: 2 }, model_versions: { v16: 1, v17: 4 }, weather_sources: { manual: 5 },
}
const render = (extra) => renderToStaticMarkup(React.createElement(SystemOverview, { ...props, ...extra }))
function elements(tree) {
  if (Array.isArray(tree)) return tree.flatMap(elements)
  if (!tree || typeof tree !== 'object') return []
  return [tree, ...elements(tree.props?.children)]
}

test('overview displays field record totals independently of a simulation result', () => {
  const html = render({ data, simData: { n_infested_final: 999999, peak_risk: 1 } })
  assert.match(html, /Inspection records/)
  assert.match(html, /Active alerts now/)
  assert.match(html, /&lt;Orchard A&gt;/)
  assert.doesNotMatch(html, /999999|Infestation rate|Estimated loss/)
  const philippineStart = new Date(data.start_at).toLocaleDateString('en-PH', {
    timeZone: 'Asia/Manila', year: 'numeric', month: 'short', day: 'numeric',
  })
  assert.ok(html.includes(philippineStart))
})

test('loading and failures hide summary cards instead of presenting zero values as successful data', () => {
  const loading = render({ loading: true })
  assert.match(loading, /role="status"/)
  assert.match(loading, /aria-busy="true"/)
  assert.doesNotMatch(loading, /Registered trees/)
  const failed = render({ error: 'Data storage unavailable', data })
  assert.match(failed, /role="alert"/)
  assert.doesNotMatch(failed, /Registered trees|Activity chart/)
})

test('background refresh leaves tables available and refresh failures identify the displayed records as older data', () => {
  const html = render({ data, refreshing: true })
  assert.match(html, /Updating saved activity/)
  assert.match(html, /id="overview-orchard-activity"/)
  assert.match(html, /Registered trees/)
  const failed = render({ data, refreshError: 'Storage unavailable' })
  assert.match(failed, /Showing the last loaded records/)
  assert.match(failed, /role="alert"/)
  assert.match(failed, /id="overview-orchard-activity"/)
})

test('empty activity still displays current inventory and active alerts', () => {
  const html = render({ data: { ...data, simulations: { ...data.simulations, total: 0, completed: 0 },
    observations: { total: 0, inspected: 0, present: 0, absent: 0, not_inspected: 0 },
    alerts: { ...data.alerts, raised: 0 } } })
  assert.match(html, /No saved activity/)
  assert.match(html, /Registered trees/)
  assert.match(html, /Active alerts now/)
})

test('History-style month picker and period menus only change Overview filters', () => {
  const actions = []
  const tree = SystemOverview({ ...props, period: 'month', orchardId: 'b', directory: [{ orchard_id: 'b', name: 'B' }],
    onPeriodChange: (value) => actions.push(['period', value]),
    onDateChange: (value) => actions.push(['date', value]),
    onOrchardChange: (value) => actions.push(['orchard', value]) })
  const nodes = elements(tree)
  assert.equal(nodes.filter((node) => node.type === 'button' && node.props['aria-pressed'] != null).length, 0)
  const datePicker = nodes.find((node) => node.props?.id === 'overview-date')
  assert.equal(datePicker.props.type, 'month')
  assert.equal(datePicker.props.value, '2024-02')
  assert.equal(datePicker.props.max, overviewDateKey().slice(0, 7))
  const period = nodes.find((node) => node.props?.id === 'overview-period')
  assert.equal(typeof period.type, 'function')
  assert.equal(period.props.value, 'month')
  assert.deepEqual(period.props.options.map((option) => option.value),
    ['day', 'week', 'month', 'year'])
  period.props.onChange('year')
  datePicker.props.onChange({ target: { value: '2025-01' } })
  datePicker.props.onChange({ target: { value: '' } })
  nodes.find((node) => node.props?.id === 'overview-orchard').props.onChange('a')
  assert.deepEqual(actions, [['period', 'year'], ['date', '2025-01-01'], ['orchard', 'a']])
  const daily = elements(SystemOverview({ ...props, period: 'day' })).find((node) => node.props?.id === 'overview-date')
  assert.equal(daily.props.type, 'date')
  assert.equal(daily.props.value, '2024-02-29')
  assert.equal(daily.props.max, overviewDateKey())
})

test('chart and accessible table use the same chronological counts including zero-activity dates', () => {
  const timeline = [
    { date: '2026-10-01', simulations: 0, observations: 0, present: 0, alerts: 0 },
    { date: '2026-10-02', simulations: 3, observations: 5, present: 2, alerts: 1 },
  ]
  const html = renderToStaticMarkup(React.createElement(Chart, { timeline, monthly: false }))
  const { data: traces, layout } = JSON.parse(html.match(/<output>(.*?)<\/output>/)[1].replaceAll('&quot;', '"'))
  assert.ok(traces.every((trace) => trace.type === 'bar'))
  assert.equal(layout.barmode, 'group')
  assert.equal(layout.yaxis.rangemode, 'tozero')
  assert.deepEqual(traces.map((trace) => trace.y), [[0, 3], [0, 5], [0, 2], [0, 1]])
  assert.ok(traces.every((trace) => JSON.stringify(trace.x) === JSON.stringify(['2026-10-01', '2026-10-02'])))
  assert.match(html, /id="overview-activity-table" hidden=""/)
  assert.match(html, /2026-10-02<\/th><td[^>]*>3<\/td><td[^>]*>5<\/td><td[^>]*>2<\/td><td[^>]*>1<\/td>/)
})

function tableRowCount(html, id) {
  const body = html.match(new RegExp(`<table id="${id}"[\\s\\S]*?<tbody>([\\s\\S]*?)</tbody>`))?.[1]
  assert.ok(body, `Missing table: ${id}`)
  return [...body.matchAll(/<tr>/g)].length
}

test('thousands of orchard rows render bounded pages with totals and accessible controls', () => {
  const orchardRows = Array.from({ length: 10003 }, (_, index) => ({ ...data.orchard_activity[0],
    orchard_id: `orchard-${index}`, name: `Orchard ${index + 1}` }))
  const html = render({ data: { ...data, orchard_activity: orchardRows } })
  assert.equal(tableRowCount(html, 'overview-orchard-activity'), 10)
  assert.match(html, /Showing 1–10 of 10,003 rows/)
  assert.match(html, /Page 1 of 1,001/)
  assert.match(html, /id="overview-orchard-activity-search"/)
  assert.match(html, /id="overview-orchard-activity-page-size"/)
  assert.match(html, /aria-sort="ascending"/)
  assert.match(html, /role="region" aria-label="Orchard activity table" tabindex="0"/)
  assert.match(html, /aria-label="Next page of orchard activity"/)
  assert.match(html, /disabled="" aria-label="Previous page of orchard activity"/)
})

test('chart keeps all daily bars when its data table is paginated and also supports a single monthly bucket', () => {
  const timeline = Array.from({ length: 31 }, (_, index) => ({
    date: `2026-10-${String(index + 1).padStart(2, '0')}`, simulations: index, observations: index + 1, present: 0, alerts: 0,
  }))
  const html = renderToStaticMarkup(React.createElement(Chart, { timeline, monthly: false }))
  const plot = JSON.parse(html.match(/<output>(.*?)<\/output>/)[1].replaceAll('&quot;', '"'))
  assert.ok(plot.data.every((trace) => trace.x.length === 31 && trace.y.length === 31))
  assert.equal(tableRowCount(html, 'overview-timeline'), 10)
  const monthly = renderToStaticMarkup(React.createElement(Chart, { timeline: timeline.slice(0, 1), monthly: true }))
  const monthPlot = JSON.parse(monthly.match(/<output>(.*?)<\/output>/)[1].replaceAll('&quot;', '"'))
  assert.ok(monthPlot.data.every((trace) => trace.type === 'bar' && trace.y.length === 1))
  assert.equal(tableRowCount(monthly, 'overview-timeline'), 1)
  assert.match(monthly, /aria-label="Sort activity counts by month"/)
})
