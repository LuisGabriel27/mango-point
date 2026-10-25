export const SESSION_IDLE_MS = 15 * 60 * 1000
export const SESSION_CHECK_MS = 30 * 1000
export const SESSION_ACTIVITY_KEY = 'mangopoint.session.lastActivity'
export const SESSION_EXPIRY_KEY = 'mangopoint.session.expiresAt'
export const SESSION_NOTICE_KEY = 'mangopoint.session.notice'
export const SESSION_USER_KEY = 'mangopoint.session.user'
export const SESSION_INVALID_EVENT = 'mangopoint:session-invalid'

export function sessionValue(storage, key) {
  try { return storage.getItem(key) } catch { return null }
}

export function storeSessionValue(storage, key, value) {
  try {
    if (value == null) storage.removeItem(key)
    else storage.setItem(key, String(value))
  } catch { /* The in-memory deadline still applies when storage is unavailable. */ }
}

// Only deliberate input renews the session. Timers, API polling, map playback,
// programmatic scrolling and returning to a tab do not count as interaction.
export function startSessionMonitor({
  storage, events, document, timers, now = Date.now, onExpire, onRefresh, onCheck,
}) {
  const saved = sessionValue(storage, SESSION_ACTIVITY_KEY)
  let lastActivity = saved != null && Number.isFinite(Number(saved)) ? Number(saved) : now()
  let lastAttempt = now(), lastWrite = lastActivity, dirty = false, pending = false, stopped = false
  let deadlineTimer
  const inputEvents = ['pointerdown', 'pointermove', 'keydown', 'wheel', 'touchstart', 'touchmove']

  const expire = () => {
    if (stopped) return true
    const expiry = sessionValue(storage, SESSION_EXPIRY_KEY)
    const idle = now() - lastActivity >= SESSION_IDLE_MS
    const tokenExpired = expiry != null && Number.isFinite(Number(expiry)) && now() >= Number(expiry)
    if (!idle && !tokenExpired) return false
    stopped = true
    onExpire(idle
      ? 'You were signed out after 15 minutes of inactivity. Please sign in again.'
      : 'Your session expired. Please sign in again.')
    return true
  }
  const scheduleDeadline = () => {
    timers.clearTimeout(deadlineTimer)
    deadlineTimer = timers.setTimeout(expire, Math.max(0, lastActivity + SESSION_IDLE_MS - now()))
  }
  const refresh = async () => {
    if (pending || expire()) return
    pending = true
    lastAttempt = now()
    const activity = lastActivity
    try {
      await onRefresh({ activity_age_seconds: Math.max(0, (now() - activity) / 1000) })
      if (!stopped && lastActivity === activity) dirty = false
    } catch { /* API 401 handling ends revoked sessions; outages never renew the deadline. */ }
    finally { pending = false }
  }
  const check = () => {
    if (pending || expire()) return
    if (dirty) { void refresh(); return }
    pending = true
    Promise.resolve().then(onCheck).catch(() => {}).finally(() => { pending = false })
  }
  const activity = (event) => {
    if (!event.isTrusted || expire()) return
    lastActivity = now()
    dirty = true
    if (now() - lastWrite >= 1000) {
      storeSessionValue(storage, SESSION_ACTIVITY_KEY, lastActivity)
      lastWrite = lastActivity
    }
    scheduleDeadline()
    if (now() - lastAttempt >= SESSION_CHECK_MS) void refresh()
  }
  const wake = () => {
    if (stopped) return
    storeSessionValue(storage, SESSION_ACTIVITY_KEY, lastActivity)
    if (document.visibilityState !== 'hidden') check()
    else expire()
  }
  storeSessionValue(storage, SESSION_ACTIVITY_KEY, lastActivity)
  for (const type of inputEvents) events.addEventListener(type, activity, { passive: true, capture: true })
  events.addEventListener('focus', wake)
  events.addEventListener('online', wake)
  document.addEventListener('visibilitychange', wake)
  const interval = timers.setInterval(() => {
    if (expire()) return
    if (document.visibilityState !== 'hidden') check()
  }, SESSION_CHECK_MS)
  if (!expire()) scheduleDeadline()
  return () => {
    stopped = true
    timers.clearInterval(interval)
    timers.clearTimeout(deadlineTimer)
    for (const type of inputEvents) events.removeEventListener(type, activity, true)
    events.removeEventListener('focus', wake)
    events.removeEventListener('online', wake)
    document.removeEventListener('visibilitychange', wake)
  }
}
