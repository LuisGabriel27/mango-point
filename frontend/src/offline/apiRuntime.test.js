import test from 'node:test'
import assert from 'node:assert/strict'

import { chooseApiTarget, resolveApiTarget, getSessionApiTarget, setSessionApiTarget,
  SESSION_API_TARGET_KEY } from './apiRuntime.js'

test('prefers the local companion whenever it is available', () => {
  assert.equal(chooseApiTarget({ localAvailable: true, internetAvailable: true }).mode, 'local')
  assert.equal(chooseApiTarget({ localAvailable: true, internetAvailable: false }).mode, 'local')
})

test('uses the remote API only when internet is available and local is absent', () => {
  assert.deepEqual(
    chooseApiTarget({
      localAvailable: false,
      internetAvailable: true,
      remoteBase: 'https://api.example.test',
    }),
    { mode: 'remote', baseURL: 'https://api.example.test' },
  )
})

test('points at the companion with an unavailable state while fully offline', () => {
  assert.equal(
    chooseApiTarget({ localAvailable: false, internetAvailable: false }).mode,
    'local-unavailable',
  )
})

test('supports the fixed production proxy and the local Vite proxy', () => {
  for (const remoteBase of ['/api', '']) {
    assert.deepEqual(
      chooseApiTarget({ localAvailable: false, internetAvailable: true, remoteBase }),
      { mode: 'remote', baseURL: remoteBase },
    )
  }
})

test('only selects a companion with a connected MangoPoint database', async (t) => {
  const originalFetch = globalThis.fetch
  t.after(() => { globalThis.fetch = originalFetch })
  for (const body of [{ status: 'healthy', database: 'error' }, { unrelated: true }]) {
    globalThis.fetch = async () => new Response(JSON.stringify(body))
    assert.equal((await resolveApiTarget({ forceProbe: true })).mode, 'remote')
  }
  globalThis.fetch = async () => new Response(JSON.stringify({ status: 'healthy', database: 'connected' }))
  assert.equal((await resolveApiTarget({ forceProbe: true })).mode, 'local')
})

test('concurrent requests share a probe and fall back when local access is denied', async (t) => {
  const originalFetch = globalThis.fetch
  t.after(() => { globalThis.fetch = originalFetch })
  let calls = 0
  globalThis.fetch = async () => {
    calls += 1
    throw new TypeError('Local network access denied')
  }
  const targets = await Promise.all(Array.from({ length: 5 }, () => resolveApiTarget({ forceProbe: true })))
  assert.equal(calls, 1)
  assert.ok(targets.every((target) => target.mode === 'remote'))
})

test('an authenticated API stays pinned across outages and changes in companion availability', async (t) => {
  const originalFetch = globalThis.fetch
  t.after(() => { globalThis.fetch = originalFetch; setSessionApiTarget(null) })
  setSessionApiTarget({ mode: 'local', baseURL: 'http://127.0.0.1:8000' })
  globalThis.fetch = async () => { throw new TypeError('Companion temporarily unavailable') }
  assert.equal((await resolveApiTarget({ forceProbe: true })).mode, 'local-unavailable')
  assert.equal((await resolveApiTarget({ forceProbe: true })).baseURL, 'http://127.0.0.1:8000')

  setSessionApiTarget({ mode: 'remote', baseURL: '' })
  globalThis.fetch = async () => new Response(JSON.stringify({ status: 'healthy', database: 'connected' }))
  assert.deepEqual(await resolveApiTarget({ forceProbe: true }), {
    mode: 'remote', baseURL: '', internetAvailable: true, localAvailable: true,
  })
  setSessionApiTarget(null)
  assert.equal((await resolveApiTarget({ forceProbe: true })).mode, 'local')
})

test('session targets survive module reload storage and ignore malformed or unconfigured URLs', (t) => {
  const originalStorage = globalThis.sessionStorage
  const values = new Map()
  globalThis.sessionStorage = { getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value), removeItem: (key) => values.delete(key) }
  t.after(() => { setSessionApiTarget(null); globalThis.sessionStorage = originalStorage })
  setSessionApiTarget(null)
  for (const saved of ['broken-json', '{"mode":"local","baseURL":"https://other.test"}', 'null']) {
    values.set(SESSION_API_TARGET_KEY, saved)
    assert.equal(getSessionApiTarget(), null)
  }
  const local = { mode: 'local', baseURL: 'http://127.0.0.1:8000' }
  values.set(SESSION_API_TARGET_KEY, JSON.stringify(local))
  assert.deepEqual(getSessionApiTarget(), local)
  setSessionApiTarget({ ...local, mode: 'local-unavailable' })
  assert.deepEqual(JSON.parse(values.get(SESSION_API_TARGET_KEY)), local)
  setSessionApiTarget(null)
  assert.equal(values.has(SESSION_API_TARGET_KEY), false)
})
