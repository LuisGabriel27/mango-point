import { expect, test } from '@playwright/test'
import { verificationForecast } from './fixtures/verificationForecast.js'

// All simulation/provider responses and account state here are isolated fixtures.
// No forecast is submitted to an actual API or saved as field evidence.
async function dashboard(page, { pest = 'cecid', mode = 'grid', saved = false, pendingSaved = false, unavailable = false } = {}) {
  const run = verificationForecast({ runId: `AI-TEST-${pest}-${mode}`, pest, mode })
  run.action_plan = [{ title: 'Inspect flagged trees', timing: 'Next field round', priority: 'High',
    scope_label: 'Tree 1', max_risk: 0.8, recommended_steps: ['Confirm field signs before treatment decisions.'] }]
  const pending = { status: 'pending', run_id: run.run_id, model: 'isolated-gemini', provider: 'Gemini',
    simulation_model_version: run.metadata.model_version, requested_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 70000).toISOString() }
  const ready = { ...pending, status: unavailable ? 'unavailable' : 'ready', reason: unavailable ? 'request_failed' : null,
    summary: 'Inspect the modeled risk locations before deciding on control.',
    explanations: [{ action_index: 0, explanation: 'Field inspection checks whether modeled pressure is present.' }] }
  run.ai_guidance = saved && !pendingSaved ? ready : pending
  const state = { run, ready, writes: [], polls: 0, generated: saved, release: null, finished: false }
  await page.addInitScript(() => sessionStorage.setItem('access_token', 'isolated-ai-guidance'))
  await page.route(/arcgisonline|tile.openstreetmap|demotiles.maplibre/, (route) => route.abort())
  await page.route(/\/(auth|orchards|weather|monitoring|simulation|observations|alerts|sync|evaluation|validation)(\/|\?|$)/, async (route) => {
    const req = route.request(), path = new URL(req.url()).pathname
    if (req.method() !== 'GET') state.writes.push({ path, method: req.method() })
    if (path === '/auth/me') return route.fulfill({ json: { user: { user_id: 7, username: 'isolated-test', role: 'operator' } } })
    if (path === '/auth/logout') return route.fulfill({ json: { message: 'Isolated session ended' } })
    if (path === '/auth/session/refresh') return route.fulfill({ json: { access_token: 'isolated-ai-guidance',
      user: { user_id: 7, username: 'isolated-test', role: 'operator' } } })
    if (path === '/orchards') return route.fulfill({ json: { orchards: [] } })
    if (path === '/weather/live') return route.fulfill({ json: { current: { temperature_c: 28, humidity: 75,
      wind_speed_ms: 1, wind_direction_deg: 90, source: 'synthetic' } } })
    if (path === '/simulation/run-simulation') {
      state.generated = true
      return route.fulfill({ json: run })
    }
    if (path === '/simulation/runs') return route.fulfill({ json: { runs: state.generated ? [run] : [] } })
    if (path === `/simulation/runs/${run.run_id}/recommendations`) {
      state.polls++
      await new Promise((resolve) => { state.release = resolve })
      run.ai_guidance = ready
      try { await route.fulfill({ json: { run_id: run.run_id, ai_guidance: ready } }) }
      catch (_) { /* Switching orchard/logout can abort the read. */ }
      finally { state.finished = true }
      return
    }
    if (path === `/simulation/runs/${run.run_id}`) return route.fulfill({ json: run })
    if (path === '/alerts') return route.fulfill({ json: { alerts: [] } })
    if (path === '/observations/list') return route.fulfill({ json: { observations: [] } })
    return route.fulfill({ status: 503, json: { detail: 'Isolated browser fixture' } })
  })
  await page.goto('/')
  await page.getByRole('button', { name: 'Maybe later', exact: true }).click()
  return state
}

for (const pest of ['cecid', 'fruitfly']) for (const mode of ['grid', 'tree_graph']) {
  test(`${pest}/${mode}: completing a simulation automatically loads guidance and caches it`, async ({ page }, testInfo) => {
    const state = await dashboard(page, { pest, mode })
    await page.locator('#sidebar-tab-simulate').click()
    await page.locator('[data-tour="pest"] button', { hasText: pest === 'cecid' ? 'Cecid Fly' : 'Fruit Fly' }).click()
    await page.getByRole('button', { name: /Model & Neighbor Pressure/ }).click()
    await page.locator('[data-tour="engine"] button', { hasText: mode === 'grid' ? 'Grid (CA)' : 'Tree Graph' }).click()
    await page.locator('#run-sim-btn').click()
    await expect.poll(() => state.polls).toBe(1)
    await page.locator('#sidebar-tab-results').click()
    const panel = page.getByRole('region', { name: 'AI recommendations', exact: true })
    await expect(panel).toContainText('Preparing AI recommendations')
    await expect(page.locator('#sidebar-panel-results')).toContainText('Confirm field signs before treatment decisions.')
    state.release()
    await expect(panel).toContainText(state.ready.summary)
    await expect(panel).not.toContainText('Preparing AI recommendations')
    await panel.scrollIntoViewIfNeeded()
    await page.screenshot({ path: testInfo.outputPath('automatic-guidance.png') })
    await page.getByRole('button', { name: 'History', exact: true }).click()
    await page.getByRole('row').filter({ hasText: state.run.run_id }).getByRole('button', { name: /Load Result/ }).click()
    await page.locator('#sidebar-tab-results').click()
    await expect(panel).toContainText(state.ready.summary)
    expect(state.polls).toBe(1)
    expect(state.writes.filter((req) => req.path !== '/auth/session/refresh')).toEqual([
      { path: '/simulation/run-simulation', method: 'POST' },
    ])
    const cached = await page.evaluate(async (id) => {
      const { getSimulationRunFromHistory } = await import('/src/utils/simulationHistoryStore.js')
      return (await getSimulationRunFromHistory(id)).ai_guidance
    }, state.run.run_id)
    expect(cached.status).toBe('ready')
  })
}

test('saved guidance is reused in a narrow layout without any generation request', async ({ page }, testInfo) => {
  const state = await dashboard(page, { saved: true })
  await page.getByRole('button', { name: 'History', exact: true }).click()
  await page.getByRole('button', { name: /Load Result/ }).click()
  await page.locator('#sidebar-tab-results').click()
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('button', { name: 'Open simulation workspace', exact: true }).click()
  const panel = page.getByRole('region', { name: 'AI recommendations', exact: true })
  await expect(panel).toContainText(state.ready.summary)
  await panel.scrollIntoViewIfNeeded()
  const box = await panel.boundingBox()
  expect(box.x).toBeGreaterThanOrEqual(0)
  expect(box.x + box.width).toBeLessThanOrEqual(390)
  await page.screenshot({ path: testInfo.outputPath('narrow-guidance.png') })
  expect(state.polls).toBe(0)
  expect(state.writes.filter((req) => req.path !== '/auth/session/refresh')).toEqual([])
})

test('an AI failure leaves the action plan and ordinary workflow usable', async ({ page }) => {
  const state = await dashboard(page, { saved: true, unavailable: true })
  await page.getByRole('button', { name: 'History', exact: true }).click()
  await page.getByRole('button', { name: /Load Result/ }).click()
  await page.locator('#sidebar-tab-results').click()
  await expect(page.getByRole('region', { name: 'AI recommendations' })).toContainText('AI guidance is unavailable')
  await expect(page.locator('#sidebar-panel-results')).toContainText('Confirm field signs before treatment decisions.')
  await page.locator('#sidebar-tab-simulate').click()
  await expect(page.locator('#run-sim-btn')).toBeEnabled()
  expect(state.writes.filter((req) => req.path !== '/auth/session/refresh')).toEqual([])
})

for (const leave of ['orchard switch', 'logout']) {
  test(`a late explanation after ${leave} cannot restore the previous result`, async ({ page }) => {
    const state = await dashboard(page, { saved: true, pendingSaved: true })
    await page.getByRole('button', { name: 'History', exact: true }).click()
    await page.getByRole('button', { name: /Load Result/ }).click()
    await expect.poll(() => state.polls).toBe(1)
    if (leave === 'orchard switch') {
      await page.locator('#sidebar-tab-setup').click()
      await page.locator('[data-tour="orchard"]').getByRole('combobox').click()
      await page.getByRole('option', { name: 'Guimaras Wonders Farm', exact: true }).click()
      await page.locator('#sidebar-tab-results').click()
      await expect(page.locator('#sidebar-panel-results')).toContainText('No simulation results yet')
    } else {
      await page.getByRole('button', { name: 'Logout', exact: true }).click()
      await page.getByRole('alertdialog', { name: 'Confirm logout' }).getByRole('button', { name: 'Log out', exact: true }).click()
      await expect.poll(() => page.evaluate(() => sessionStorage.getItem('access_token'))).toBe(null)
    }
    state.release()
    await expect.poll(() => state.finished).toBe(true)
    await expect(page.getByRole('region', { name: 'AI recommendations' })).toHaveCount(0)
    expect(state.writes.filter((req) => req.path !== '/auth/session/refresh')).toEqual(
      leave === 'logout' ? [{ path: '/auth/logout', method: 'POST' }] : [],
    )
  })
}
