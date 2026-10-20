import { sessionValue, storeSessionValue } from '../utils/sessionMonitor.js'

const DEFAULT_LOCAL_API_BASE = 'http://127.0.0.1:8000'
const LOCAL_PROBE_TTL_MS = 15_000
const LOCAL_PROBE_TIMEOUT_MS = 2_500

const runtimeEnv = import.meta.env || {}
// Production uses a project-level Vercel rewrite. Its destination can change
// without rebuilding this bundle or invalidating an installed PWA.
const remoteApiBase = String(runtimeEnv.VITE_API_BASE || (runtimeEnv.PROD ? '/api' : '')).replace(/\/$/, '')
const localApiBase = String(
  runtimeEnv.VITE_LOCAL_API_BASE || DEFAULT_LOCAL_API_BASE,
).replace(/\/$/, '')

export const SESSION_API_TARGET_KEY = 'mangopoint.session.apiTarget'
let sessionTarget = null

export function getSessionApiTarget() {
  if (sessionTarget) return { ...sessionTarget }
  try {
    const saved = JSON.parse(sessionValue(globalThis.sessionStorage, SESSION_API_TARGET_KEY))
    if ((saved?.mode === 'local' && saved.baseURL === localApiBase)
        || (saved?.mode === 'remote' && saved.baseURL === remoteApiBase)) return saved
  } catch { /* A session from an older release may not have a saved target. */ }
  return null
}

export function setSessionApiTarget(target) {
  sessionTarget = target ? {
    mode: target.mode.startsWith('local') ? 'local' : 'remote', baseURL: target.baseURL,
  } : null
  storeSessionValue(globalThis.sessionStorage, SESSION_API_TARGET_KEY,
    sessionTarget ? JSON.stringify(sessionTarget) : null)
}

let probeState = {
  checkedAt: 0,
  localAvailable: false,
  pending: null,
}

let connectionState = {
  mode: 'checking',
  baseURL: remoteApiBase,
  internetAvailable: typeof navigator === 'undefined' ? true : navigator.onLine !== false,
  localAvailable: false,
}

const listeners = new Set()

function publish(next) {
  const changed = Object.keys(next).some((key) => connectionState[key] !== next[key])
  connectionState = { ...connectionState, ...next }
  if (changed) listeners.forEach((listener) => listener(connectionState))
  return connectionState
}

export function getConnectionState() {
  return { ...connectionState }
}

export function subscribeConnectionState(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function chooseApiTarget({ localAvailable, internetAvailable, remoteBase = remoteApiBase }) {
  if (localAvailable) {
    return { mode: 'local', baseURL: localApiBase }
  }
  if (internetAvailable) {
    return { mode: 'remote', baseURL: remoteBase }
  }
  return { mode: 'local-unavailable', baseURL: localApiBase }
}

async function probeLocalApi(force = false) {
  const now = Date.now()
  if (!force && now - probeState.checkedAt < LOCAL_PROBE_TTL_MS) {
    return probeState.localAvailable
  }
  if (probeState.pending) return probeState.pending

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), LOCAL_PROBE_TIMEOUT_MS)
  probeState.pending = fetch(`${localApiBase}/health`, {
    method: 'GET',
    mode: 'cors',
    cache: 'no-store',
    signal: controller.signal,
    // Chromium uses this to request permission for a public HTTPS PWA to
    // connect to its local companion. Other browsers safely ignore it.
    targetAddressSpace: 'loopback',
  })
    .then(async (response) => {
      if (!response.ok) return false
      const health = await response.json()
      return health.status === 'healthy' && health.database === 'connected'
    })
    .catch(() => false)
    .finally(() => {
      clearTimeout(timer)
      probeState.checkedAt = Date.now()
      probeState.pending = null
    })

  probeState.localAvailable = await probeState.pending
  return probeState.localAvailable
}

export async function resolveApiTarget({ forceProbe = false } = {}) {
  const internetAvailable = typeof navigator === 'undefined' ? true : navigator.onLine !== false
  const localAvailable = await probeLocalApi(forceProbe)
  // Session rows and signing keys belong to the issuing API. A lost health
  // probe must not move its bearer token (or farm writes) to another database.
  const pinned = getSessionApiTarget()
  const target = pinned
    ? { ...pinned, mode: pinned.mode === 'local' && !localAvailable ? 'local-unavailable' : pinned.mode }
    : chooseApiTarget({ localAvailable, internetAvailable })
  return publish({ ...target, internetAvailable, localAvailable })
}

export function localFetchOptions(config = {}) {
  return {
    ...(config.fetchOptions || {}),
    targetAddressSpace: 'loopback',
  }
}

if (typeof window !== 'undefined') {
  const refresh = () => {
    probeState.checkedAt = 0
    resolveApiTarget({ forceProbe: true }).catch(() => {})
  }
  window.addEventListener('online', refresh)
  window.addEventListener('offline', refresh)
}
