import { test, expect } from '@playwright/test'
import { verificationForecast } from './fixtures/verificationForecast.js'

async function dashboard(page, runs = []) {
  const writes = [], observations = []
  await page.addInitScript(() => { sessionStorage.setItem('access_token', 'isolated-verification-test') })
  await page.route(/\/(auth|orchards|weather|monitoring|simulation|observations|alerts|sync|evaluation|validation)(\/|\?|$)/, async (route) => {
    const request = route.request(), path = new URL(request.url()).pathname
    if (request.method() !== 'GET') {
      const body = request.postDataJSON()
      writes.push({ path, body })
      if (path === '/observations/submit-observation') {
        observations.push({ ...body, id: observations.length + 1 })
        return route.fulfill({ json: observations.at(-1) })
      }
      return route.fulfill({ status: 400, json: { detail: 'Isolated verification test: unexpected write' } })
    }
    if (path === '/auth/me') return route.fulfill({ json: { user: { user_id: 'verification-test', username: 'test', role: 'scout' } } })
    if (path === '/orchards') return route.fulfill({ json: { orchards: [] } })
    if (path === '/simulation/runs') return route.fulfill({ json: { runs } })
    const saved = runs.find((run) => path === `/simulation/runs/${run.run_id}`)
    if (saved) return route.fulfill({ json: saved })
    if (path === '/observations/list') return route.fulfill({ json: { observations } })
    if (path === '/alerts') return route.fulfill({ json: { alerts: [] } })
    return route.fulfill({ status: 503, json: { detail: 'Isolated verification test: service unavailable' } })
  })
  await page.goto('/')
  await page.getByRole('button', { name: 'Maybe later', exact: true }).click()
  return writes
}

async function load(page, runId) {
  await page.getByRole('button', { name: 'History', exact: true }).click()
  await page.locator('tr').filter({ hasText: runId }).getByRole('button', { name: /Load Result/ }).click()
  await page.locator('#sidebar-tab-verify').click()
  await expect(page.getByRole('note')).toContainText(runId)
}

test('Verify has no inspection form or write action without a completed forecast', async ({ page }) => {
  const writes = await dashboard(page)
  await page.locator('#sidebar-tab-verify').click()
  await expect(page.getByText('Load a forecast to verify it', { exact: true })).toBeVisible()
  await expect(page.locator('#observation-notes')).toHaveCount(0)
  await expect(page.getByRole('button', { name: /Record .*inspection/ })).toHaveCount(0)
  await page.getByRole('button', { name: 'Open Simulate', exact: true }).click()
  await expect(page.locator('#sidebar-tab-simulate')).toHaveAttribute('aria-selected', 'true')
  expect(writes).toEqual([])
})

for (const pest of ['cecid', 'fruitfly']) {
  for (const mode of ['grid', 'tree_graph']) {
    test(`${pest} / ${mode}: saved forecast unlocks Verify and every inspection stays linked`, async ({ page }) => {
      const run = verificationForecast({ runId: `${pest}-${mode}-sample`, pest, mode })
      const writes = await dashboard(page, [run])
      await load(page, run.run_id)
      await expect(page.locator('#observation-pest')).toHaveAttribute('readonly', '')
      await page.locator('#observation-tree-ids').fill('1')
      await page.locator('#observation-notes').fill('ISOLATED TEST ONLY · no actual field inspection')
      await page.getByRole('button', { name: /Record 1 inspection/ }).click()
      await expect(page.locator('.observation-result').filter({ hasText: 'recorded' })).toBeVisible()
      expect(writes).toHaveLength(1)
      expect(writes[0].body.simulation_run_id).toBe(run.run_id)
      expect(writes[0].body.observed_pest).toBe(pest)
      expect(writes[0].body.forecast_risk).toBeNull()
      expect(writes[0].body.forecast_lead_hours).toBeNull()
      await expect(page.locator('.observation-history-link')).toContainText(run.run_id)
    })
  }
}

test('switching loaded runs clears the inspection draft and binds the actual forecast pest', async ({ page }) => {
  const a = verificationForecast({ runId: 'first-forecast', pest: 'cecid' })
  const b = verificationForecast({ runId: 'second-forecast', pest: 'fruitfly' })
  const writes = await dashboard(page, [a, b])
  await load(page, a.run_id)
  await page.getByRole('button', { name: 'Tree 1', exact: true }).click()
  await page.getByRole('button', { name: /Log field verification for this tree/ }).click()
  await expect(page.locator('#observation-tree-ids')).toHaveValue('1')
  await page.locator('#observation-notes').fill('Draft for first forecast only')
  await load(page, b.run_id)
  await expect(page.locator('#observation-tree-ids')).toHaveValue('')
  await expect(page.locator('#observation-notes')).toHaveValue('')
  await expect(page.locator('#observation-pest')).toHaveValue('Oriental Fruit Fly')
  await page.locator('#sidebar-tab-simulate').click()
  await page.locator('[data-tour="pest"] button', { hasText: 'Cecid Fly' }).click()
  await page.locator('#sidebar-tab-verify').click()
  await expect(page.locator('#observation-pest')).toHaveValue('Oriental Fruit Fly')
  await page.locator('#observation-tree-ids').fill('2')
  await page.getByRole('button', { name: /Record 1 inspection/ }).click()
  await expect(page.locator('.observation-result').filter({ hasText: 'recorded' })).toBeVisible()
  expect(writes[0].body.simulation_run_id).toBe(b.run_id)
  expect(writes[0].body.observed_pest).toBe('fruitfly')
})

test('a selected map tree keeps its prediction, but typing another tree clears that prediction', async ({ page }) => {
  const run = verificationForecast({ pest: 'fruitfly' })
  const writes = await dashboard(page, [run])
  await load(page, run.run_id)
  await page.getByRole('button', { name: 'Tree 1', exact: true }).click()
  await page.getByRole('button', { name: /Log field verification for this tree/ }).click()
  await expect(page.locator('#observation-tree-ids')).toHaveValue('1')
  await expect(page.getByRole('note')).toContainText('Hour 47')
  await page.getByRole('button', { name: /Record 1 inspection/ }).click()
  await expect(page.locator('.observation-result').filter({ hasText: 'recorded' })).toBeVisible()
  expect(writes[0].body.forecast_risk).toBe(0.8)
  expect(writes[0].body.forecast_lead_hours).toBe(47)
  expect(writes[0].body.lon).toBeCloseTo(122.5806)
  expect(writes[0].body.lat).toBe(10.584)
  await page.locator('#observation-tree-ids').fill('2')
  await expect(page.getByRole('note')).not.toContainText('Hour 47')
  await page.getByRole('button', { name: /Record 1 inspection/ }).click()
  await expect.poll(() => writes.length).toBe(2)
  expect(writes[1].body.simulation_run_id).toBe(run.run_id)
  for (const field of ['forecast_risk', 'forecast_lead_hours', 'lon', 'lat']) expect(writes[1].body[field]).toBeNull()
})
