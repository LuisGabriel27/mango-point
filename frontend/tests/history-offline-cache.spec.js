import { expect, test } from '@playwright/test'
import { verificationForecast } from './fixtures/verificationForecast.js'

// Isolated API fixtures: no farm record, forecast or verification is created.
async function openDashboard(page, { failingId = null, holdId = null } = {}) {
  page.setDefaultTimeout(10000)
  const runs = ['cecid', 'fruitfly'].flatMap((pest) => ['grid', 'tree_graph'].map((mode) => ({
    ...verificationForecast({ runId: `UNOPENED-${pest}-${mode}`, pest, mode,
      orchardId: mode === 'grid' ? 'default-orchard' : 'other-orchard' }),
    started_at: '2025-01-02T00:00:00Z', weather_source: 'manual',
  })))
  const state = { offline: false, failingId, holdId, release: null, detailReads: [], writes: [], sessionRefreshes: [] }
  const user = { user_id: 'offline-cache-test', username: 'manager', role: 'operator' }
  await page.addInitScript(() => sessionStorage.setItem('access_token', 'isolated-offline-history'))
  await page.route(/arcgisonline|tile.openstreetmap|demotiles.maplibre/, (route) => route.abort())
  await page.route(/\/(health|auth|orchards|weather|monitoring|simulation|observations|alerts|sync|evaluation|validation)(\/|\?|$)/, async (route) => {
    const request = route.request(), path = new URL(request.url()).pathname
    // Reconnection may renew a session after real input. This is authentication
    // maintenance, separate from the farm-record writes this fixture forbids.
    if (path === '/auth/session/refresh' && request.method() === 'POST') {
      const body = request.postDataJSON()
      state.sessionRefreshes.push(body)
      return route.fulfill({ json: { access_token: 'isolated-offline-history', user,
        expires_at: new Date(await page.evaluate(() => Date.now())
          + (900 - body.activity_age_seconds) * 1000).toISOString() } })
    }
    if (request.method() !== 'GET') {
      state.writes.push({ method: request.method(), path })
      return route.fulfill({ status: 400, json: { detail: 'Unexpected fixture write' } })
    }
    if (path === '/auth/me') return route.fulfill({ json: { user } })
    if (path === '/health') return route.fulfill({ json: { status: 'healthy', database: 'connected' } })
    if (path === '/orchards') return route.fulfill({ json: { orchards: [
      { orchard_id: 'other-orchard', name: 'Other test orchard', tree_geojson: runs[1].risk_geojson },
    ] } })
    if (path === '/alerts') return route.fulfill({ json: { alerts: [] } })
    if (path === '/simulation/runs') {
      if (state.offline) return route.abort()
      // Summaries deliberately exclude all result payloads.
      return route.fulfill({ json: { runs: runs.map(({ risk_geojson, time_series, request_payload, metadata, ...summary }) => summary), deleted_run_ids: [] } })
    }
    const run = runs.find((entry) => path === `/simulation/runs/${entry.run_id}`)
    if (run) {
      state.detailReads.push(run.run_id)
      if (run.run_id === state.holdId) await new Promise((resolve) => { state.release = resolve })
      if (state.offline || run.run_id === state.failingId) return route.abort()
      return route.fulfill({ json: run })
    }
    return route.fulfill({ status: 503, json: { detail: 'Isolated offline History fixture' } })
  })
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: 'Maybe later', exact: true }).click()
  const connectionClose = page.getByRole('button', { name: 'Close connection status', exact: true })
  if (await connectionClose.isVisible()) await connectionClose.click()
  return { runs, state }
}

async function cachedRecords(page) {
  return page.evaluate(async () => {
    const { getSimulationRunFromHistory, listSimulationRunsFromHistory } = await import('/src/utils/simulationHistoryStore.js')
    const summaries = await listSimulationRunsFromHistory({ limit: Infinity })
    return Promise.all(summaries.map((row) => getSimulationRunFromHistory(row.run_id)))
  })
}

test('unopened results across both pests/engines and orchards load offline after automatic preparation', async ({ page }, testInfo) => {
  const { runs, state } = await openDashboard(page)
  // Stay on Live Map: History and Load Result have never been opened.
  await expect.poll(async () => (await cachedRecords(page)).length).toBe(4)
  expect(new Set(state.detailReads).size).toBe(4)
  const records = await cachedRecords(page)
  for (const run of runs) {
    const cached = records.find((row) => row.run_id === run.run_id)
    expect(cached.risk_geojson).toEqual(run.risk_geojson)
    expect(cached.time_series).toEqual(run.time_series)
    expect(cached.metadata).toEqual(run.metadata)
    expect(cached.request_payload.random_seed).toBe(42)
  }
  expect(state.writes).toEqual([])
  state.offline = true
  await page.context().setOffline(true)
  await page.getByRole('button', { name: 'Close connection status', exact: true }).click()
  await page.getByRole('button', { name: 'History', exact: true }).click()
  await page.getByRole('button', { name: 'All history', exact: true }).click()
  await page.locator('#ops-panel-history').getByRole('button', { name: /Refresh$/ }).click()
  await expect(page.getByTestId('history-offline-status')).toContainText('4 results available offline')
  for (const run of runs) {
    // Verify requires choosing the forecast's orchard through ordinary Setup.
    await page.getByRole('button', { name: 'Live Map', exact: true }).click()
    await page.locator('#sidebar-tab-setup').click()
    await page.locator('[data-tour="orchard"]').getByRole('combobox').click()
    await page.getByRole('option').filter({ hasText: run.orchard_id === 'default-orchard' ? 'Default Orchard (BPI)' : 'Other test orchard' }).click()
    await page.getByRole('button', { name: 'History', exact: true }).click()
    const row = page.locator('tr').filter({ hasText: run.run_id })
    await expect(row).toContainText('Available offline')
    await row.getByRole('button', { name: /Load Result$/ }).click()
    await page.locator('#sidebar-tab-verify').click()
    await expect(page.getByRole('note')).toContainText(run.run_id)
    await page.getByRole('button', { name: 'History', exact: true }).click()
  }
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.getByTestId('history-offline-status')).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('offline-history-narrow.png') })
  expect(state.writes).toEqual([])
})

test('incomplete preparation is visible and reconnection retries only missing results', async ({ page }) => {
  const id = 'UNOPENED-cecid-tree_graph'
  const { state } = await openDashboard(page, { failingId: id })
  await page.getByRole('button', { name: 'History', exact: true }).click()
  await page.getByRole('button', { name: 'All history', exact: true }).click()
  await expect(page.getByTestId('history-offline-status')).toContainText('Some results could not be prepared')
  await expect(page.locator('tr').filter({ hasText: id })).toContainText('Online only')
  const firstReads = state.detailReads.filter((entry) => entry === 'UNOPENED-cecid-grid').length
  state.failingId = null
  await page.evaluate(() => window.dispatchEvent(new Event('online')))
  await expect(page.getByTestId('history-offline-status')).toHaveText('4 of 4 results available offline in this browser across all orchards.')
  expect(state.detailReads.filter((entry) => entry === 'UNOPENED-cecid-grid').length).toBe(firstReads)
  expect(state.writes).toEqual([])
})

test('logout cancels preparation without caching a delayed detail', async ({ page }) => {
  const id = 'UNOPENED-cecid-grid'
  const { state } = await openDashboard(page, { holdId: id })
  await expect.poll(() => state.release !== null).toBe(true)
  await page.evaluate(async () => {
    const { SESSION_INVALID_EVENT } = await import('/src/utils/sessionMonitor.js')
    window.dispatchEvent(new CustomEvent(SESSION_INVALID_EVENT, {
      detail: { token: sessionStorage.getItem('access_token'), message: 'Isolated session end' },
    }))
  })
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible()
  state.release()
  // A subsequent read provides a transaction boundary after the aborted fetch.
  expect(await cachedRecords(page)).toEqual([])
  expect(state.detailReads).toEqual([id])
  expect(state.writes).toEqual([])
})

test('results saved to fallback storage remain loadable when IndexedDB reads still work', async ({ page }) => {
  await page.addInitScript(() => {
    const original = IDBDatabase.prototype.transaction
    IDBDatabase.prototype.transaction = function (...args) {
      if (this.name === 'mangopoint-history-cache' && args[1] === 'readwrite') throw new Error('Isolated quota failure')
      return original.apply(this, args)
    }
  })
  const { state } = await openDashboard(page)
  await expect.poll(async () => (await cachedRecords(page)).filter(Boolean).length).toBe(4)
  const count = await page.evaluate(() => JSON.parse(localStorage.getItem('mangopoint.simulationHistory.v1')).length)
  expect(count).toBe(4)
  expect(state.writes).toEqual([])
})
