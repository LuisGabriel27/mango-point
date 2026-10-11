import test from 'node:test'
import assert from 'node:assert/strict'
import { failOverviewLoad, overviewDateKey, requestSystemOverview, startOverviewLoad } from './systemOverview.js'

const tick = () => new Promise((resolve) => setImmediate(resolve))
const deferred = () => {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

test('changing the selected date prevents an older response replacing the current period', async () => {
  const old = deferred(), current = deferred(), results = [], errors = [], requests = []
  const load = (params, signal) => {
    requests.push({ params, signal })
    return params.date === '2024-02-29' ? old.promise : current.promise
  }
  const cancel = requestSystemOverview(load, { period: 'month', date: '2024-02-29' }, (value) => results.push(value), (error) => errors.push(error))
  await tick()
  cancel()
  const finish = requestSystemOverview(load, { period: 'month', date: '2025-01-01', orchard_id: 'b' },
    (value) => results.push(value), (error) => errors.push(error))
  await tick()
  current.resolve({ data: { period: 'month', selected_date: '2025-01-01', orchard_id: 'b' } })
  await tick()
  old.resolve({ data: { period: 'month', selected_date: '2024-02-29' } })
  await tick()
  assert.deepEqual(results, [{ period: 'month', selected_date: '2025-01-01', orchard_id: 'b' }])
  assert.deepEqual(errors, [])
  assert.equal(requests[0].signal.aborted, true)
  assert.deepEqual(requests[1].params, { period: 'month', date: '2025-01-01', orchard_id: 'b' })
  finish()
})

test('tab exit suppresses cancellation errors; an active storage failure is reported', async () => {
  const pending = deferred(), errors = []
  const cancel = requestSystemOverview(() => pending.promise, { period: 'month' },
    () => assert.fail('Unexpected data'), (error) => errors.push(error.message))
  await tick()
  cancel()
  pending.reject(new Error('Canceled'))
  await tick()
  assert.deepEqual(errors, [])
  requestSystemOverview(() => Promise.reject(new Error('Storage unavailable')), { period: 'month' },
    () => assert.fail('Unexpected data'), (error) => errors.push(error.message))
  await tick()
  assert.deepEqual(errors, ['Storage unavailable'])
})

test('cleanup before loading prevents an unnecessary request', async () => {
  let calls = 0
  requestSystemOverview(() => { calls++; return Promise.resolve({ data: {} }) }, {},
    () => assert.fail('Unexpected data'), () => assert.fail('Unexpected error'))()
  await tick()
  assert.equal(calls, 0)
})

test('date picker uses today in Philippine time at day and year boundaries', () => {
  assert.equal(overviewDateKey(new Date('2026-10-10T16:00:00Z')), '2026-10-11')
  assert.equal(overviewDateKey(new Date('2025-12-31T15:59:59Z')), '2025-12-31')
  assert.equal(overviewDateKey(new Date('2025-12-31T16:00:00Z')), '2026-01-01')
})

test('refresh keeps the same scope mounted, while changing dates removes the older summary', () => {
  const previous = { key: 'month::2024-02-29', loading: false, data: { computed_at: '2026-10-10T08:00:00Z' }, error: '' }
  const refresh = startOverviewLoad(previous, previous.key)
  assert.equal(refresh.loading, false)
  assert.equal(refresh.refreshing, true)
  assert.equal(refresh.data, previous.data)
  const differentDate = startOverviewLoad(previous, 'month::2025-01-01')
  assert.equal(differentDate.loading, true)
  assert.equal(differentDate.refreshing, false)
  assert.equal(differentDate.data, null)
  assert.equal(previous.loading, false)
})

test('refresh failure retains the last good summary and timestamp but an initial failure has no data', () => {
  const previous = { key: 'week::2024-02-29', loading: false, data: { computed_at: '2026-10-10T08:00:00Z' }, error: '' }
  const failedRefresh = failOverviewLoad(startOverviewLoad(previous, previous.key), previous.key, 'Storage unavailable')
  assert.equal(failedRefresh.data, previous.data)
  assert.equal(failedRefresh.refreshing, false)
  assert.equal(failedRefresh.refreshError, 'Storage unavailable')
  assert.equal(failedRefresh.error, '')
  const initialFailure = failOverviewLoad(previous, 'week::2025-01-01', 'Storage unavailable')
  assert.equal(initialFailure.data, null)
  assert.equal(initialFailure.error, 'Storage unavailable')
  assert.equal(initialFailure.loading, false)
})
