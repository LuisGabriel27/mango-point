const DB_NAME = 'mangopoint-history-cache'
const DB_VERSION = 1
const STORE_NAME = 'simulation_runs'
const FALLBACK_KEY = 'mangopoint.simulationHistory.v1'
const FALLBACK_LIMIT = 25
const DEFAULT_ORCHARD_ID = 'default-orchard'

let dbPromise = null

function browserWindow() {
  return typeof window !== 'undefined' ? window : null
}

function normalizeId(value, fallback = DEFAULT_ORCHARD_ID) {
  const text = String(value ?? '').trim()
  return text || fallback
}

function parseMaybeJson(value, fallback) {
  if (value == null) return fallback
  if (typeof value !== 'string') return value
  try {
    return JSON.parse(value)
  } catch (_) {
    return fallback
  }
}

function generatedRunId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID()
  }
  return `local-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

function dateValue(value) {
  const time = new Date(value ?? 0).getTime()
  return Number.isFinite(time) ? time : 0
}

function sortNewestFirst(a, b) {
  return (
    dateValue(b.started_at || b.local_saved_at)
    - dateValue(a.started_at || a.local_saved_at)
  )
}

function openDb() {
  const win = browserWindow()
  if (!win?.indexedDB) {
    return Promise.reject(new Error('IndexedDB is not available.'))
  }

  if (dbPromise) return dbPromise

  dbPromise = new Promise((resolve, reject) => {
    const request = win.indexedDB.open(DB_NAME, DB_VERSION)

    request.onupgradeneeded = () => {
      const db = request.result
      const store = db.objectStoreNames.contains(STORE_NAME)
        ? request.transaction.objectStore(STORE_NAME)
        : db.createObjectStore(STORE_NAME, { keyPath: 'run_id' })

      if (!store.indexNames.contains('orchard_id')) {
        store.createIndex('orchard_id', 'orchard_id', { unique: false })
      }
      if (!store.indexNames.contains('started_at')) {
        store.createIndex('started_at', 'started_at', { unique: false })
      }
    }

    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error('Could not open history cache.'))
    request.onblocked = () => reject(new Error('History cache upgrade was blocked.'))
  })

  dbPromise.catch(() => {
    dbPromise = null
  })

  return dbPromise
}

function txStore(mode, action) {
  return openDb().then((db) => new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, mode)
    const store = tx.objectStore(STORE_NAME)
    let request

    try {
      request = action(store)
    } catch (error) {
      reject(error)
      return
    }

    tx.oncomplete = () => resolve(request?.result)
    tx.onerror = () => reject(tx.error ?? new Error('History cache transaction failed.'))
    tx.onabort = () => reject(tx.error ?? new Error('History cache transaction aborted.'))
  }))
}

function readFallbackHistory() {
  const win = browserWindow()
  if (!win?.localStorage) return []

  try {
    const stored = JSON.parse(win.localStorage.getItem(FALLBACK_KEY) || '[]')
    return Array.isArray(stored) ? stored : []
  } catch (_) {
    return []
  }
}

function writeFallbackHistory(records) {
  const win = browserWindow()
  if (!win?.localStorage) return

  const sorted = [...records].sort(sortNewestFirst).slice(0, FALLBACK_LIMIT)
  let next = sorted

  while (next.length) {
    try {
      win.localStorage.setItem(FALLBACK_KEY, JSON.stringify(next))
      return
    } catch (_) {
      next = next.slice(0, -1)
    }
  }
}

function inferWeatherSource(run, requestPayload) {
  if (run.weather_source || run.history?.weather_source) {
    return run.weather_source || run.history.weather_source
  }
  if (
    requestPayload.manual_weather
    || requestPayload.manual_weather_series
    || requestPayload.manual_weather_blocks
  ) {
    return 'manual'
  }
  return 'open-meteo'
}

export function normalizeSimulationRunForHistory(run) {
  const now = new Date().toISOString()
  const requestPayload = parseMaybeJson(run?.request_payload ?? run?.input_parameters, {})
  const metadata = parseMaybeJson(run?.metadata, {})
  const history = parseMaybeJson(run?.history, {})
  const runId = normalizeId(run?.run_id ?? metadata.run_id, generatedRunId())
  const orchardId = normalizeId(
    run?.orchard_id
      ?? history.orchard_id
      ?? requestPayload.orchard_id,
  )

  const detail = {
    ...(run || {}),
    run_id: runId,
    orchard_id: orchardId,
    pest_type: run?.pest_type ?? requestPayload.pest_type ?? metadata.pest_type,
    simulation_mode: (
      run?.simulation_mode
      ?? metadata.simulation_mode
      ?? requestPayload.simulation_mode
      ?? 'grid'
    ),
    hours: run?.hours ?? requestPayload.hours,
    started_at: run?.started_at ?? history.started_at ?? metadata.started_at ?? now,
    completed_at: run?.completed_at ?? history.completed_at ?? metadata.completed_at,
    duration_seconds: run?.duration_seconds ?? history.duration_seconds,
    status: run?.status ?? history.status ?? 'completed',
    peak_risk: run?.peak_risk,
    cells_at_risk: run?.cells_at_risk,
    n_infested_final: run?.n_infested_final,
    weather_source: inferWeatherSource({ ...(run || {}), history }, requestPayload),
    request_payload: requestPayload,
    input_parameters: requestPayload,
    metadata,
    local_saved_at: run?.local_saved_at ?? now,
  }

  detail.has_time_series = Boolean(
    run?.has_time_series
      || (Array.isArray(detail.time_series) && detail.time_series.length)
      || (Array.isArray(detail.response_payload?.time_series) && detail.response_payload.time_series.length),
  )

  return detail
}

export function simulationRunSummaryFromDetail(detail) {
  return {
    run_id: detail.run_id,
    pest_type: detail.pest_type,
    orchard_id: detail.orchard_id,
    simulation_mode: detail.simulation_mode,
    hours: detail.hours,
    started_at: detail.started_at,
    completed_at: detail.completed_at,
    status: detail.status,
    peak_risk: detail.peak_risk,
    cells_at_risk: detail.cells_at_risk,
    n_infested_final: detail.n_infested_final,
    weather_source: detail.weather_source,
    has_time_series: detail.has_time_series,
    local_saved_at: detail.local_saved_at,
    cached_locally: true,
  }
}

export async function saveSimulationRunToHistory(run) {
  const detail = normalizeSimulationRunForHistory(run)

  try {
    await txStore('readwrite', (store) => store.put(detail))
  } catch (_) {
    const existing = readFallbackHistory().filter((item) => item.run_id !== detail.run_id)
    writeFallbackHistory([detail, ...existing])
  }

  return simulationRunSummaryFromDetail(detail)
}

export async function listSimulationRunsFromHistory({ orchardId, limit = 50 } = {}) {
  let records = []

  try {
    records = await txStore('readonly', (store) => store.getAll())
  } catch (_) {
    records = readFallbackHistory()
  }

  const normalizedOrchardId = orchardId ? normalizeId(orchardId) : null
  return (records || [])
    .map(normalizeSimulationRunForHistory)
    .filter((run) => !normalizedOrchardId || run.orchard_id === normalizedOrchardId)
    .sort(sortNewestFirst)
    .slice(0, limit)
    .map(simulationRunSummaryFromDetail)
}

export async function getSimulationRunFromHistory(runId) {
  if (!runId) return null

  let detail = null
  try {
    detail = await txStore('readonly', (store) => store.get(runId))
  } catch (_) {
    detail = readFallbackHistory().find((item) => item.run_id === runId) ?? null
  }

  if (!detail) return null
  const normalized = normalizeSimulationRunForHistory(detail)
  return {
    ...normalized,
    loaded_from_history: true,
    history: {
      run_id: normalized.run_id,
      orchard_id: normalized.orchard_id,
      started_at: normalized.started_at,
      completed_at: normalized.completed_at,
      duration_seconds: normalized.duration_seconds,
      status: normalized.status,
      weather_source: normalized.weather_source,
      local_cache: true,
    },
  }
}
