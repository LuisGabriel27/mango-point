import test from 'node:test'
import assert from 'node:assert/strict'
import { syncSimulationHistory } from './simulationHistorySync.js'
import { normalizeSimulationRunForHistory, simulationRunSummaryFromDetail } from './simulationHistoryStore.js'

const run = (id, extra = {}) => ({ run_id: id, orchard_id: 'default-orchard', status: 'completed',
  pest_type: 'cecid', simulation_mode: 'grid', started_at: '2026-10-19T00:00:00Z', ...extra })
const detail = (summary) => ({ ...summary, risk_geojson: { type: 'FeatureCollection', features: [] },
  time_series: [{ hour: 1 }], weather_data: [{ temperature_c: 28 }],
  request_payload: { random_seed: 42 }, metadata: { model_version: 'original-version' } })

function fixture(runs, existing = []) {
  const records = new Map(existing.map((record) => [record.run_id, record]))
  const calls = [], updates = []
  const api = {
    async getSimulationRuns(params, config) {
      calls.push({ kind: 'list', params, config })
      return { data: { runs: runs.slice(params.offset, params.offset + params.limit), total: 1, deleted_run_ids: [] },
        config: { authTarget: { baseURL: '/issuing-api', mode: 'remote' } } }
    },
    async getSimulationRun(id, config) {
      calls.push({ kind: 'detail', id, config })
      return { data: detail(runs.find((row) => row.run_id === id)) }
    },
  }
  const store = {
    async list() { return [...records.values()].filter((record) => record.status !== 'deleted')
      .map((record) => simulationRunSummaryFromDetail(normalizeSimulationRunForHistory(record))) },
    async save(record) {
      if (records.get(record.run_id)?.status === 'deleted') return records.get(record.run_id)
      records.set(record.run_id, record)
      return simulationRunSummaryFromDetail(normalizeSimulationRunForHistory(record))
    },
    async setDeleted(ids, deleted) {
      for (const id of ids) {
        const record = records.get(id)
        if (deleted) records.set(id, { ...record, run_id: id, status: 'deleted' })
        else if (record?.status === 'deleted') records.set(id, { ...record, status: 'completed' })
      }
    },
  }
  return { api, store, calls, updates, records, options: { api, store, onUpdate: (state) => updates.push(state) } }
}

test('prepares unopened results for both pests/engines, all orchards/dates, and preserves saved evidence', async () => {
  const runs = ['cecid', 'fruitfly'].flatMap((pest_type) => ['grid', 'tree_graph'].map((simulation_mode) =>
    run(`${pest_type}-${simulation_mode}`, { pest_type, simulation_mode, orchard_id: simulation_mode,
      started_at: '2025-01-01T00:00:00Z' })))
  const f = fixture(runs)
  await syncSimulationHistory(f.options)
  assert.equal(f.updates.at(-1).phase, 'ready')
  assert.equal(f.updates.at(-1).runs.filter((row) => row.cached_locally).length, 4)
  for (const summary of runs) assert.deepEqual(f.records.get(summary.run_id), detail(summary))
  assert.ok(f.calls.filter((call) => call.kind === 'detail').every((call) => call.config.authTarget.baseURL === '/issuing-api'))
  assert.equal(f.calls[0].params.orchard_id, undefined)
  f.calls.length = 0
  await syncSimulationHistory(f.options)
  assert.equal(f.calls.filter((call) => call.kind === 'detail').length, 0, 'does not download complete cached runs again')
})

test('pages beyond 1000 records and ignores the API page total as a grand total', async () => {
  const f = fixture(Array.from({ length: 1005 }, (_, i) => run(`run-${i}`)))
  await syncSimulationHistory(f.options)
  assert.equal(f.calls.filter((call) => call.kind === 'list').length, 11)
  assert.equal(f.updates.at(-1).runs.length, 1005)
  assert.ok(f.updates.at(-1).runs.every((row) => row.cached_locally))
})

test('partial preparation retries missing results after a connection failure', async () => {
  const f = fixture([run('first'), run('second'), run('third')])
  const original = f.api.getSimulationRun
  f.api.getSimulationRun = async (id, config) => {
    if (id === 'second') throw Object.assign(new Error('Network Error'), { code: 'ERR_NETWORK' })
    return original(id, config)
  }
  await syncSimulationHistory(f.options)
  assert.equal(f.updates.at(-1).phase, 'partial')
  assert.deepEqual([...f.records.keys()], ['first'])
  f.api.getSimulationRun = original
  f.calls.length = 0
  await syncSimulationHistory(f.options)
  assert.deepEqual(f.calls.filter((call) => call.kind === 'detail').map((call) => call.id), ['second', 'third'])
  assert.equal(f.updates.at(-1).phase, 'ready')
})

test('deleted and missing runs stay hidden; a restore without output is downloaded', async () => {
  const f = fixture([run('restored'), run('vanished')], [detail(run('deleted')), { run_id: 'restored', status: 'deleted' }])
  const list = f.api.getSimulationRuns
  f.api.getSimulationRuns = async (...args) => {
    const res = await list(...args)
    res.data.deleted_run_ids = ['deleted']
    return res
  }
  const get = f.api.getSimulationRun
  f.api.getSimulationRun = async (id, config) => {
    if (id === 'vanished') throw { response: { status: 404 } }
    return get(id, config)
  }
  await syncSimulationHistory(f.options)
  assert.deepEqual(f.updates.at(-1).runs.map((row) => row.run_id), ['restored'])
  assert.equal(f.records.get('restored').metadata.model_version, 'original-version')
  assert.equal(f.records.get('vanished').status, 'deleted')
})

test('cancellation after an in-flight response prevents saving and requesting further details', async () => {
  const f = fixture([run('a'), run('b')]), controller = new AbortController()
  f.api.getSimulationRun = async () => { controller.abort(); return { data: detail(run('a')) } }
  await assert.rejects(syncSimulationHistory({ ...f.options, signal: controller.signal }), { name: 'AbortError' })
  assert.equal(f.records.size, 0)
})

test('authorization failures stop preparation immediately', async () => {
  const f = fixture([run('denied'), run('never-requested')])
  const error = { response: { status: 403 } }
  f.api.getSimulationRun = async () => { throw error }
  await assert.rejects(syncSimulationHistory(f.options), (err) => err === error)
  assert.equal(f.records.size, 0)
})

test('quota failures and summary-only records cannot claim offline readiness', async () => {
  const f = fixture([run('summary-only')], [run('summary-only')])
  f.store.save = async () => { throw new Error('Browser storage is full') }
  await syncSimulationHistory(f.options)
  const state = f.updates.at(-1)
  assert.equal(state.phase, 'partial')
  assert.equal(state.runs[0].cached_locally, false)
  assert.match(state.error.message, /storage is full/)
})

test('failed records are listed without attempting to prepare a nonexistent result', async () => {
  const f = fixture([run('failed', { status: 'failed' })])
  await syncSimulationHistory(f.options)
  assert.equal(f.calls.filter((call) => call.kind === 'detail').length, 0)
  assert.equal(f.updates.at(-1).runs[0].cached_locally, false)
})
