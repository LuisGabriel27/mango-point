// Read-only polling of an already queued explanation. Never starts generation.
function delay(ms, signal) {
  return new Promise((resolve, reject) => {
    const abort = () => { clearTimeout(timer); reject(signal.reason || new Error('Aborted')) }
    const timer = setTimeout(() => { signal?.removeEventListener('abort', abort); resolve() }, ms)
    signal?.addEventListener('abort', abort, { once: true })
    if (signal?.aborted) abort()
  })
}

export async function watchSimulationGuidance({ runId, guidance, fetchGuidance, onUpdate, signal,
  intervalMs = 1500, now = Date.now, wait = delay }) {
  if (!runId || guidance?.status !== 'pending' || guidance.run_id !== runId) return
  const savedDeadline = Date.parse(guidance.expires_at)
  // Bound old or malformed cached pending states, too.
  const deadline = Math.min(Number.isFinite(savedDeadline) ? savedDeadline : 0, now() + 75000)
  const unavailable = (reason) => {
    if (!signal?.aborted) onUpdate({ ...guidance, status: 'unavailable', reason }, false)
  }
  let failures = 0
  while (!signal?.aborted && now() < deadline) {
    try {
      const { data } = await fetchGuidance(runId, { signal, timeout: 10000 })
      if (signal?.aborted) return
      if (data?.run_id !== runId || data?.ai_guidance?.run_id !== runId) {
        unavailable('request_failed')
        return
      }
      const next = data.ai_guidance
      if (['ready', 'unavailable'].includes(next.status)) {
        onUpdate(next, true)
        return
      }
      if (next.status !== 'pending') { unavailable('request_failed'); return }
      failures = 0
    } catch (error) {
      if (signal?.aborted) return
      failures += 1
      if ([401, 403, 404, 410].includes(error.response?.status) || failures >= 3) {
        unavailable('request_failed')
        return
      }
    }
    try { await wait(Math.min(intervalMs, Math.max(0, deadline - now())), signal) } catch (_) { return }
  }
  if (!signal?.aborted) unavailable('expired')
}
