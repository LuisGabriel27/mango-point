import { expect, test } from '@playwright/test'
import { verificationForecast } from './fixtures/verificationForecast.js'

// All records and API mutations in this file are isolated browser fixtures.
async function openHistory(page, { pest = 'fruitfly', mode = 'grid', width = 1440 } = {}) {
  const run = { ...verificationForecast({ runId: `DELETE-TEST-${pest}-${mode}`, pest, mode }),
    started_at: new Date().toISOString(), status: 'completed', weather_source: 'manual' }
  const other = { ...run, run_id: 'KEEP-THIS-RUN' }
  const state = { run, other, deleted: false, failDelete: false, holdDelete: null, writes: [], offline: false, missingDetails: false }
  // Open History with the existing desktop navigation, then exercise its narrow
  // layout. The current navbar hides its tab strip at phone widths.
  await page.setViewportSize({ width: 1440, height: 844 })
  await page.addInitScript(() => sessionStorage.setItem('access_token', 'isolated-history-deletion'))
  await page.route(/arcgisonline|tile.openstreetmap|demotiles.maplibre/, (route) => route.abort())
  await page.route(/\/(health|auth|orchards|weather|monitoring|simulation|observations|alerts|sync|evaluation|validation)(\/|\?|$)/, async (route) => {
    const request = route.request(), path = new URL(request.url()).pathname
    if (request.method() !== 'GET') state.writes.push({ method: request.method(), path })
    if (path === '/auth/me') return route.fulfill({ json: { user: { user_id: 7, username: 'history-test', role: 'operator' } } })
    if (path === '/health') return route.fulfill({ json: { status: 'healthy', database: 'connected' } })
    if (path === '/orchards') return route.fulfill({ json: { orchards: [] } })
    if (path === '/alerts') return route.fulfill({ json: { alerts: [] } })
    if (path === '/simulation/runs') {
      if (state.offline) return route.abort()
      return route.fulfill({ json: { runs: state.deleted ? [other] : [run, other], deleted_run_ids: state.deleted ? [run.run_id] : [] } })
    }
    if (path === `/simulation/runs/${run.run_id}`) {
      if (request.method() === 'DELETE') {
        if (state.holdDelete) await state.holdDelete()
        if (state.failDelete) return route.fulfill({ status: 503, json: { detail: 'Deletion unavailable. Try again.' } })
        state.deleted = true
        return route.fulfill({ json: { run_id: run.run_id, deleted: true, status: 'deleted' } })
      }
      if (state.deleted || state.missingDetails) return route.fulfill({ status: 404, json: { detail: 'Simulation run not found' } })
      return route.fulfill({ json: run })
    }
    if (path === `/simulation/runs/${run.run_id}/restore`) {
      state.deleted = false
      return route.fulfill({ json: { run_id: run.run_id, deleted: false, status: 'completed' } })
    }
    if (request.method() !== 'GET') return route.fulfill({ status: 400, json: { detail: 'Unexpected test write.' } })
    return route.fulfill({ status: 503, json: { detail: 'Isolated History check.' } })
  })
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: 'Maybe later', exact: true }).click()
  await page.getByRole('button', { name: 'Close connection status', exact: true }).click()
  await page.getByRole('button', { name: 'History', exact: true }).click()
  await expect(page.getByRole('button', { name: `Delete simulation ${run.run_id}`, exact: true })).toBeEnabled()
  await page.setViewportSize({ width, height: 844 })
  return state
}

async function cacheRun(page, run) {
  await page.evaluate(async (record) => {
    const store = await import('/src/utils/simulationHistoryStore.js')
    await store.saveSimulationRunToHistory(record)
  }, run)
}

for (const pest of ['cecid', 'fruitfly']) {
  for (const mode of ['grid', 'tree_graph']) {
    test(`${pest}/${mode}: confirmation protects the selected run, soft deletion persists, and Undo restores it`, async ({ page }, testInfo) => {
      const state = await openHistory(page, { pest, mode, width: mode === 'grid' ? 1440 : 390 })
      await cacheRun(page, state.run)
      const remove = page.getByRole('button', { name: `Delete simulation ${state.run.run_id}`, exact: true })
      const dialog = page.getByRole('alertdialog', { name: 'Delete saved simulation?', exact: true })
      for (const dismiss of ['cancel', 'escape', 'close', 'backdrop']) {
        await remove.click()
        await expect(dialog).toContainText(state.run.run_id)
        await expect(dialog.getByRole('button', { name: 'Cancel', exact: true })).toBeFocused()
        expect(state.writes).toEqual([])
        if (dismiss === 'cancel') await dialog.getByRole('button', { name: 'Cancel', exact: true }).click()
        else if (dismiss === 'escape') await page.keyboard.press('Escape')
        else if (dismiss === 'close') await dialog.getByRole('button', { name: 'Close simulation deletion confirmation', exact: true }).click()
        else await page.locator('.confirmation-modal-backdrop').click({ position: { x: 2, y: 2 } })
        await expect(dialog).toHaveCount(0)
        await expect(remove).toBeFocused()
      }
      await remove.click()
      const box = await dialog.boundingBox()
      expect(box.x).toBeGreaterThanOrEqual(0)
      expect(box.x + box.width).toBeLessThanOrEqual(page.viewportSize().width)
      await page.screenshot({ path: testInfo.outputPath('delete-confirmation.png') })
      await dialog.getByRole('button', { name: 'Delete simulation', exact: true }).click()
      await expect(remove).toHaveCount(0)
      await expect(page.getByRole('button', { name: 'Delete simulation KEEP-THIS-RUN', exact: true })).toBeVisible()
      expect(state.writes).toEqual([{ method: 'DELETE', path: `/simulation/runs/${state.run.run_id}` }])
      await page.getByRole('button', { name: 'Undo delete', exact: true }).click()
      await expect(remove).toBeEnabled()
      expect(state.writes.at(-1)).toEqual({ method: 'POST', path: `/simulation/runs/${state.run.run_id}/restore` })
      await remove.click()
      await dialog.getByRole('button', { name: 'Delete simulation', exact: true }).click()
      await expect(remove).toHaveCount(0)
      await page.setViewportSize({ width: 1440, height: 844 })
      await page.reload({ waitUntil: 'domcontentloaded' })
      const toast = page.getByRole('button', { name: 'Close connection status', exact: true })
      if (await toast.isVisible()) await toast.click()
      await page.getByRole('button', { name: 'History', exact: true }).click()
      await expect(page.locator('.simulation-history-table')).toContainText('KEEP-THIS-RUN')
      await expect(remove).toHaveCount(0)
      state.offline = true
      await page.getByRole('button', { name: /Refresh$/ }).click()
      await expect(remove).toHaveCount(0)
    })
  }
}

test('failed deletion keeps the row and confirmation; a held request cannot be submitted twice', async ({ page }) => {
  const state = await openHistory(page)
  const remove = page.getByRole('button', { name: `Delete simulation ${state.run.run_id}`, exact: true })
  const dialog = page.getByRole('alertdialog', { name: 'Delete saved simulation?', exact: true })
  state.failDelete = true
  await remove.click()
  await dialog.getByRole('button', { name: 'Delete simulation', exact: true }).click()
  await expect(dialog.getByRole('alert')).toContainText('Deletion unavailable')
  await expect(remove).toHaveCount(1)
  state.failDelete = false
  let release
  state.holdDelete = () => new Promise((resolve) => { release = resolve })
  await dialog.getByRole('button', { name: 'Delete simulation', exact: true }).click()
  await expect.poll(() => Boolean(release)).toBe(true)
  try {
    await expect(dialog.getByRole('button', { name: 'Cancel', exact: true })).toBeDisabled()
    await page.keyboard.press('Escape')
    await expect(dialog).toBeVisible()
    expect(state.writes).toHaveLength(2)
  } finally { release() }
  await expect(dialog).toHaveCount(0)
  await expect(remove).toHaveCount(0)
})

test('server tombstones clear a stale browser copy deleted on another device', async ({ page }) => {
  const state = await openHistory(page)
  await cacheRun(page, state.run)
  state.deleted = true
  await page.getByRole('button', { name: /Refresh$/ }).click()
  await expect(page.getByRole('button', { name: `Delete simulation ${state.run.run_id}`, exact: true })).toHaveCount(0)
  state.offline = true
  await page.reload({ waitUntil: 'domcontentloaded' })
  const toast = page.getByRole('button', { name: 'Close connection status', exact: true })
  if (await toast.isVisible()) await toast.click()
  await page.getByRole('button', { name: 'History', exact: true }).click()
  await expect(page.locator('.simulation-history-table')).toHaveCount(0)
})

test('a missing server detail never reloads the deleted result from cache', async ({ page }) => {
  const state = await openHistory(page)
  await cacheRun(page, state.run)
  state.missingDetails = true
  await page.getByRole('row').filter({ hasText: state.run.run_id }).getByRole('button', { name: /Load Result$/ }).click()
  await expect(page.getByText('This saved simulation is no longer available in History.', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: `Delete simulation ${state.run.run_id}`, exact: true })).toHaveCount(0)
  expect(state.writes).toEqual([])
})

test('a fallback deletion marker still hides readable IndexedDB output after a write failure', async ({ page }) => {
  const state = await openHistory(page)
  await cacheRun(page, state.run)
  await page.evaluate(() => {
    window.originalHistoryTransaction = IDBDatabase.prototype.transaction
    IDBDatabase.prototype.transaction = function (...args) {
      if (this.name === 'mangopoint-history-cache' && args[1] === 'readwrite') throw new Error('Isolated write failure')
      return window.originalHistoryTransaction.apply(this, args)
    }
  })
  const remove = page.getByRole('button', { name: `Delete simulation ${state.run.run_id}`, exact: true })
  await remove.click()
  await page.getByRole('alertdialog').getByRole('button', { name: 'Delete simulation', exact: true }).click()
  await expect(remove).toHaveCount(0)
  await page.evaluate(() => { IDBDatabase.prototype.transaction = window.originalHistoryTransaction })
  state.offline = true
  await page.getByRole('button', { name: /Refresh$/ }).click()
  await expect(page.locator('#ops-panel-history .alert')).toBeVisible()
  await expect(remove).toHaveCount(0)
})
