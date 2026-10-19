import {
  listSimulationRunsFromHistory,
  saveSimulationRunToHistory,
  setSimulationHistoryDeleted,
} from './simulationHistoryStore.js'

const PAGE_SIZE = 100
const REQUEST_TIMEOUT = 20000
const browserStore = {
  list: listSimulationRunsFromHistory,
  save: saveSimulationRunToHistory,
  setDeleted: setSimulationHistoryDeleted,
}

export function mergeHistoryRuns(serverRuns = [], cachedRuns = []) {
  const byId = new Map(cachedRuns.map((run) => [run.run_id, run]))
  for (const run of serverRuns) {
    const cached = byId.get(run.run_id)
    byId.set(run.run_id, { ...cached, ...run,
      cached_locally: Boolean(cached?.cached_locally), server_saved: true })
  }
  return [...byId.values()].sort((a, b) => (
    new Date(b.started_at || b.local_saved_at || 0) - new Date(a.started_at || a.local_saved_at || 0)
  ))
}

// Only authenticated GETs are used. The dashboard mounts History even when its
// tab is hidden, so preparation does not depend on opening a result or a tab.
export async function syncSimulationHistory({ api, signal, onUpdate, store = browserStore }) {
  const check = () => signal?.throwIfAborted()
  let cached = await store.list({ limit: Infinity })
  check()
  onUpdate({ runs: cached, phase: 'checking' })
  const server = new Map()
  const deleted = new Set()
  let authTarget
  for (let offset = 0; ; offset += PAGE_SIZE) {
    check()
    const response = await api.getSimulationRuns({ limit: PAGE_SIZE, offset },
      { signal, timeout: REQUEST_TIMEOUT, authTarget })
    check()
    // Keep every page and detail on the API that supplied this history list.
    authTarget ??= response.config?.authTarget
    const page = response.data?.runs
    if (!Array.isArray(page)) throw new Error('The server did not return simulation history.')
    for (const id of response.data.deleted_run_ids ?? []) deleted.add(id)
    for (const run of page) if (run?.run_id) server.set(run.run_id, run)
    if (page.length < PAGE_SIZE) break
  }
  for (const id of deleted) server.delete(id)
  let storageError = null
  try {
    await store.setDeleted([...deleted], true)
    check()
    await store.setDeleted([...server.keys()], false)
  } catch (error) {
    check()
    storageError = error
  }
  check()
  // Re-read after restore/deletion reconciliation; restored markers alone are
  // not full results and must still be downloaded.
  cached = await store.list({ limit: Infinity })
  check()
  const cache = new Map(cached.filter((run) => !deleted.has(run.run_id)).map((run) => [run.run_id, run]))
  const publish = (phase, error = null) => {
    check()
    onUpdate({ runs: mergeHistoryRuns([...server.values()], [...cache.values()]), phase, error })
  }
  publish('downloading')
  let downloadError = null
  for (const run of server.values()) {
    check()
    if (run.status !== 'completed' || cache.get(run.run_id)?.cached_locally) continue
    let detail
    try {
      const response = await api.getSimulationRun(run.run_id, { signal, timeout: REQUEST_TIMEOUT, authTarget })
      check()
      detail = response.data
      if (detail?.run_id !== run.run_id || !detail.risk_geojson) {
        throw new Error('A saved simulation has no complete result map available.')
      }
    } catch (error) {
      check()
      const status = error.response?.status
      if ([401, 403].includes(status)) throw error
      if ([404, 410].includes(status)) {
        deleted.add(run.run_id)
        server.delete(run.run_id)
        cache.delete(run.run_id)
        await store.setDeleted([run.run_id], true).catch((err) => { storageError = err })
        publish('downloading')
        continue
      }
      downloadError = error
      // Stop a disconnected batch promptly; a failed individual record does
      // not prevent the remaining available results from being prepared.
      if ((!error.response && error.code !== undefined) || [502, 503, 504].includes(status)) break
      continue
    }
    check()
    try {
      const summary = await store.save(detail, { requirePersistence: true })
      check()
      if (summary.status === 'deleted') {
        deleted.add(run.run_id)
        server.delete(run.run_id)
        cache.delete(run.run_id)
      } else cache.set(run.run_id, summary)
    } catch (error) {
      check()
      storageError = error
      break
    }
    publish('downloading')
  }
  // The small localStorage fallback can evict entries to stay within quota.
  // Report what actually remains durable, not how many downloads succeeded.
  cached = await store.list({ limit: Infinity })
  check()
  cache.clear()
  for (const run of cached) if (!deleted.has(run.run_id)) cache.set(run.run_id, run)
  const incomplete = [...server.values()].some((run) => run.status === 'completed' && !cache.get(run.run_id)?.cached_locally)
  publish(incomplete || storageError || downloadError ? 'partial' : 'ready', storageError || downloadError)
}
