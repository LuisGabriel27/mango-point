import { test, expect } from '@playwright/test'
import { readFile, mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'
import { verificationForecast } from './fixtures/verificationForecast.js'

async function reportDialog(page, { pest = 'fruitfly', mode = 'tree_graph', missingImage = false } = {}) {
  const run = verificationForecast({ runId: `PDF-SAMPLE-${pest}-${mode}`, pest, mode })
  run.request_payload.dashboard_state = { report_orchard: { name: 'PDF EXPORT SAMPLE ONLY' } }
  if (missingImage) run.request_payload.dashboard_state.report_orchard.orthophoto_overlay = {
    url: '/missing-report-test.png', coordinates: [[122.5793, 10.5861], [122.5827, 10.5861], [122.5827, 10.5827], [122.5793, 10.5827]],
  }
  const writes = [], basemaps = []
  await page.addInitScript(() => { sessionStorage.setItem('access_token', 'isolated-pdf-export-test') })
  await page.route(/arcgisonline|tile.openstreetmap/, async (route) => {
    basemaps.push(route.request().url())
    await route.abort()
  })
  await page.route(/\/(auth|orchards|weather|monitoring|simulation|observations|alerts|sync|evaluation|validation)(\/|\?|$)/, async (route) => {
    const request = route.request(), path = new URL(request.url()).pathname
    if (request.method() !== 'GET') {
      if (path === '/auth/session/refresh') return route.fulfill({ json: {
        access_token: 'isolated-pdf-export-test', expires_at: new Date(Date.now() + 900000).toISOString(),
        user: { user_id: 'pdf-test', username: 'test', role: 'operator' },
      } })
      writes.push(path)
      return route.fulfill({ status: 400, json: { detail: 'Unexpected test write.' } })
    }
    if (path === '/auth/me') return route.fulfill({ json: { user: { user_id: 'pdf-test', username: 'test', role: 'operator' } } })
    if (path === '/orchards') return route.fulfill({ json: { orchards: [] } })
    if (path === '/simulation/runs') return route.fulfill({ json: { runs: [run] } })
    if (path === `/simulation/runs/${run.run_id}`) return route.fulfill({ json: run })
    if (path === '/alerts') return route.fulfill({ json: { alerts: [] } })
    return route.fulfill({ status: 503, json: { detail: 'Isolated PDF export test.' } })
  })
  await page.goto('/')
  await page.getByRole('button', { name: 'Maybe later', exact: true }).click()
  await page.getByRole('button', { name: 'History', exact: true }).click()
  await page.getByRole('button', { name: /Print report/ }).click()
  await expect(page.getByRole('dialog', { name: 'Prepare simulation report' })).toBeVisible()
  await page.getByLabel('Field notes', { exact: true }).fill('PDF EXPORT TEST ONLY - no field inspection performed.')
  return { writes, basemaps }
}

for (const pest of ['cecid', 'fruitfly']) {
  for (const mode of ['grid', 'tree_graph']) {
    test(`${pest} / ${mode}: Save as PDF downloads a real document without opening print`, async ({ page }) => {
      const { writes } = await reportDialog(page, { pest, mode })
      let popups = 0
      page.on('popup', () => { popups++ })
      const downloadPromise = page.waitForEvent('download')
      await page.getByRole('button', { name: 'Save as PDF', exact: true }).click()
      const download = await downloadPromise
      expect(download.suggestedFilename()).toMatch(/\.pdf$/)
      const output = resolve('../outputs/pdf-download-checks')
      await mkdir(output, { recursive: true })
      const path = resolve(output, `${pest}-${mode}.pdf`)
      await download.saveAs(path)
      const bytes = await readFile(path)
      expect(bytes.subarray(0, 5).toString()).toBe('%PDF-')
      expect(bytes.length).toBeGreaterThan(20000)
      expect(popups).toBe(0)
      await expect(page.getByRole('button', { name: 'Save as PDF', exact: true })).toBeEnabled()
      await expect(page.locator('iframe[title="Preparing PDF report"]')).toHaveCount(0)
      expect(writes).toEqual([])
    })
  }
}

test('detailed tables and long notes still download a complete PDF', async ({ page }) => {
  await reportDialog(page)
  await page.getByLabel('Include detailed tables', { exact: false }).check()
  await expect(page.getByRole('dialog', { name: 'Prepare simulation report' })).toBeVisible()
  await page.locator('#report-fieldNotes').fill('LAYOUT SAMPLE ONLY - no actual field inspection. '.repeat(60))
  await page.locator('#report-plannedActions').fill('SAMPLE FOLLOW-UP - verify page breaks; no action was performed. '.repeat(45))
  const pending = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Save as PDF', exact: true }).click()
  const download = await pending
  await download.saveAs(resolve('../outputs/pdf-download-checks/long-notes.pdf'))
  const bytes = await readFile(await download.path())
  expect(bytes.subarray(0, 5).toString()).toBe('%PDF-')
  await expect(page.getByRole('button', { name: 'Save as PDF', exact: true })).toBeEnabled()
})

test('Print opens the report tab, calls print and uses the plain Print label', async ({ page, context }) => {
  await context.addInitScript(() => { window.print = () => { window.printRequested = true } })
  const { writes } = await reportDialog(page)
  const popupPromise = page.waitForEvent('popup')
  await page.getByRole('button', { name: 'Print', exact: true }).click()
  const popup = await popupPromise
  await expect(popup.getByRole('button', { name: 'Print', exact: true })).toBeVisible()
  await expect.poll(() => popup.evaluate(() => Boolean(window.printRequested))).toBe(true)
  expect(await popup.locator('body').innerText()).not.toContain('Print / Save PDF')
  expect(writes).toEqual([])
})

test('a missing orthophoto reports an error and never downloads a blank PDF', async ({ page }) => {
  await page.route('**/missing-report-test.png', (route) => route.fulfill({ status: 404, body: 'Missing test image' }))
  await reportDialog(page, { missingImage: true })
  const downloads = []
  page.on('download', (download) => downloads.push(download))
  await page.getByRole('button', { name: 'Save as PDF', exact: true }).click()
  await expect(page.getByRole('alert').filter({ hasText: 'orthophoto could not be loaded' })).toBeVisible()
  expect(downloads).toEqual([])
  await expect(page.getByRole('button', { name: 'Save as PDF', exact: true })).toBeEnabled()
})
