import test from 'node:test'
import assert from 'node:assert/strict'
import { watchSimulationGuidance } from './aiGuidance.js'

function fixture(overrides = {}) {
  let time = 0
  const updates = [], calls = [], controller = new AbortController()
  const guidance = { run_id: 'run-a', status: 'pending', expires_at: new Date(5000).toISOString() }
  const ready = { ...guidance, status: 'ready', summary: 'Inspect the modeled risk locations.' }
  const options = { runId: 'run-a', guidance, signal: controller.signal,
    fetchGuidance: async (id, config) => { calls.push({ id, config }); return { data: { run_id: id, ai_guidance: ready } } },
    onUpdate: (...args) => updates.push(args), now: () => time,
    wait: async (ms) => { time += ms }, ...overrides }
  return { options, updates, calls, controller, ready }
}

test('polls only pending jobs and retains completed guidance without regeneration', async () => {
  for (const status of [undefined, 'ready', 'unavailable']) {
    const f = fixture({ guidance: status ? { run_id: 'run-a', status } : null })
    await watchSimulationGuidance(f.options)
    assert.equal(f.calls.length, 0)
  }
  const f = fixture()
  await watchSimulationGuidance(f.options)
  assert.deepEqual(f.updates, [[f.ready, true]])
  assert.equal(f.calls[0].id, 'run-a')
  assert.equal(f.calls[0].config.signal, f.controller.signal)
})

test('expires a restarted job and bounds unavailable network retries without caching transient failures', async () => {
  const expired = fixture({ guidance: { run_id: 'run-a', status: 'pending', expires_at: 'invalid' } })
  await watchSimulationGuidance(expired.options)
  assert.equal(expired.calls.length, 0)
  assert.equal(expired.updates[0][0].reason, 'expired')
  let calls = 0
  const offline = fixture({ fetchGuidance: async () => { calls++; throw new Error('offline') } })
  await watchSimulationGuidance(offline.options)
  assert.equal(calls, 3)
  assert.equal(offline.updates[0][1], false)
})

test('a late response after orchard switching/logout cannot update state or cache', async () => {
  const f = fixture()
  f.options.fetchGuidance = async () => {
    f.controller.abort()
    return { data: { run_id: 'run-a', ai_guidance: f.ready } }
  }
  await watchSimulationGuidance(f.options)
  assert.deepEqual(f.updates, [])
})

test('rejects another run and stops on authentication errors', async () => {
  const wrong = fixture({ fetchGuidance: async () => ({ data: { run_id: 'run-b', ai_guidance: { status: 'ready' } } }) })
  await watchSimulationGuidance(wrong.options)
  assert.equal(wrong.updates[0][0].status, 'unavailable')
  assert.equal(wrong.updates[0][1], false)
  let calls = 0
  const denied = fixture({ fetchGuidance: async () => { calls++; throw { response: { status: 401 } } } })
  await watchSimulationGuidance(denied.options)
  assert.equal(calls, 1)
})

test('pending responses stop at the deadline and server failures retain the existing plan', async () => {
  const f = fixture()
  f.options.fetchGuidance = async () => ({ data: { run_id: 'run-a', ai_guidance: f.options.guidance } })
  await watchSimulationGuidance(f.options)
  assert.equal(f.updates[0][0].reason, 'expired')
  const unavailable = fixture()
  unavailable.options.fetchGuidance = async () => ({ data: { run_id: 'run-a', ai_guidance: { ...unavailable.options.guidance, status: 'unavailable', reason: 'invalid_response' } } })
  await watchSimulationGuidance(unavailable.options)
  assert.equal(unavailable.updates[0][1], true)
})
