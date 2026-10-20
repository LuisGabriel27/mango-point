import test from 'node:test'
import assert from 'node:assert/strict'
import { SESSION_IDLE_MS, SESSION_ACTIVITY_KEY, SESSION_EXPIRY_KEY, startSessionMonitor } from './sessionMonitor.js'

function environment({ lastActivity, hidden = false, refreshFails = false } = {}) {
  let time = 1700000000000, nextId = 0
  const tasks = new Map(), values = new Map(), expired = [], refreshes = [], checks = []
  const target = () => ({ listeners: new Map(),
    addEventListener(type, handler) { this.listeners.set(type, handler) },
    removeEventListener(type) { this.listeners.delete(type) },
    emit(type, trusted = true) { this.listeners.get(type)?.({ isTrusted: trusted }) },
  })
  const events = target(), document = { ...target(), visibilityState: hidden ? 'hidden' : 'visible' }
  const storage = { getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)), removeItem: (key) => values.delete(key) }
  storage.setItem(SESSION_ACTIVITY_KEY, lastActivity ?? time)
  storage.setItem(SESSION_EXPIRY_KEY, time + SESSION_IDLE_MS)
  const timers = {
    setTimeout(fn, delay) { const id = ++nextId; tasks.set(id, { fn, at: time + delay }); return id },
    clearTimeout(id) { tasks.delete(id) },
    setInterval(fn, delay) { const id = ++nextId; tasks.set(id, { fn, at: time + delay, interval: delay }); return id },
    clearInterval(id) { tasks.delete(id) },
  }
  const stop = startSessionMonitor({ storage, events, document, timers, now: () => time,
    onExpire: (reason) => expired.push(reason), onCheck: async () => checks.push(time),
    onRefresh: async (body) => {
      refreshes.push(body)
      if (refreshFails) throw new Error('Server unreachable')
      storage.setItem(SESSION_EXPIRY_KEY, time + SESSION_IDLE_MS - body.activity_age_seconds * 1000)
    },
  })
  return { expired, refreshes, checks, events, document, storage, stop,
    jump(ms) { time += ms },
    async advance(ms) {
      const end = time + ms
      while (true) {
        const next = [...tasks].sort((a, b) => a[1].at - b[1].at)[0]
        if (!next || next[1].at > end) break
        const [id, task] = next
        time = task.at
        if (task.interval) task.at += task.interval
        else tasks.delete(id)
        task.fn()
        for (let count = 0; count < 6; count++) await Promise.resolve()
      }
      time = end
    },
  }
}

test('background session checks never renew an idle session; it ends at fifteen minutes', async () => {
  const env = environment()
  await env.advance(SESSION_IDLE_MS - 1)
  assert.equal(env.expired.length, 0)
  assert.ok(env.checks.length > 0)
  assert.equal(env.refreshes.length, 0)
  await env.advance(1)
  assert.match(env.expired[0], /15 minutes of inactivity/)
  env.stop()
})

test('real interaction keeps a session active without a fixed fifteen-minute login limit', async () => {
  const env = environment()
  await env.advance(14 * 60000)
  env.events.emit('keydown')
  await env.advance(SESSION_IDLE_MS - 1)
  assert.equal(env.expired.length, 0)
  assert.ok(env.refreshes.length > 0)
  await env.advance(1)
  assert.match(env.expired[0], /15 minutes of inactivity/)
  env.stop()
})

test('a reload cannot reset an already expired inactivity deadline', () => {
  const env = environment({ lastActivity: 1700000000000 - SESSION_IDLE_MS })
  assert.match(env.expired[0], /15 minutes of inactivity/)
  assert.equal(env.refreshes.length, 0)
  env.stop()
})

test('returning from a suspended tab checks expiry before accepting new input', () => {
  const env = environment({ hidden: true })
  env.jump(SESSION_IDLE_MS + 1)
  env.document.visibilityState = 'visible'
  env.events.emit('focus')
  env.events.emit('pointerdown')
  assert.equal(env.expired.length, 1)
  assert.equal(env.refreshes.length, 0)
  env.stop()
})

test('synthetic interaction and automatic scrolling do not renew the deadline', async () => {
  const env = environment()
  await env.advance(14 * 60000)
  env.events.emit('pointermove', false)
  env.events.emit('scroll')
  await env.advance(60000)
  assert.equal(env.refreshes.length, 0)
  assert.equal(env.expired.length, 1)
  env.stop()
})

test('failed renewal cannot prolong server token validity', async () => {
  const env = environment({ refreshFails: true })
  await env.advance(14 * 60000)
  env.events.emit('wheel')
  await env.advance(60000)
  assert.match(env.expired[0], /session expired/)
  env.stop()
})

test('reconnection validates the session immediately without counting as user activity', async () => {
  const env = environment()
  await env.advance(1000)
  env.events.emit('online', false)
  await env.advance(0)
  assert.equal(env.checks.length, 1)
  assert.equal(env.refreshes.length, 0)
  await env.advance(SESSION_IDLE_MS - 1000)
  assert.match(env.expired[0], /15 minutes of inactivity/)
  env.stop()
})

test('reconnection retries pending user activity without resetting its age', async () => {
  const env = environment({ refreshFails: true })
  await env.advance(SESSION_IDLE_MS - 60000)
  env.events.emit('keydown')
  await env.advance(1000)
  const attempts = env.refreshes.length
  env.events.emit('online', false)
  await env.advance(0)
  assert.equal(env.refreshes.length, attempts + 1)
  assert.equal(env.refreshes.at(-1).activity_age_seconds, 1)
  assert.equal(env.expired.length, 0)
  env.stop()
})

test('cleanup removes timers and listeners so a signed-out session cannot resume', async () => {
  const env = environment()
  env.stop()
  env.events.emit('pointerdown')
  await env.advance(SESSION_IDLE_MS * 2)
  assert.equal(env.checks.length, 0)
  assert.equal(env.refreshes.length, 0)
  assert.equal(env.expired.length, 0)
  assert.equal(env.document.listeners.size, 0)
})
