import { expect, test } from '@playwright/test'
import { verificationForecast } from './fixtures/verificationForecast.js'

const alertRecipients = [
  { recipient_id: 1, name: 'Wisz', email: 'wiszgabriel@example.com', is_active: true },
  { recipient_id: 2, name: 'Jim', email: 'jimloyd@example.com', is_active: false },
  { recipient_id: 3, name: 'Earl', email: 'earljondexter@example.com', is_active: false },
  { recipient_id: 4, name: 'Durbs', email: 'allysseus@example.com', is_active: false },
  { recipient_id: 5, name: 'Cy', email: 'cyriljohn@example.com', is_active: false },
]

// Isolated browser fixtures: never sent to the backend or saved as farm evidence.
async function openDashboard(page, { failures = false, storageBlocked = false, role = 'scout', forecast = null } = {}) {
  const requests = []
  await page.addInitScript(({ storageBlocked }) => {
    sessionStorage.setItem('access_token', 'isolated-browser-test')
    if (storageBlocked) {
      Object.defineProperty(window, 'localStorage', { get() { throw new Error('Storage unavailable') } })
    }
  }, { storageBlocked })
  await page.route(/\/(auth|orchards|weather|monitoring|simulation|observations|alerts|sync|evaluation|validation)(\/|\?|$)/, async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    requests.push({ method: request.method(), path })
    if (path === '/auth/me') return route.fulfill({ json: { user: { user_id: 'tutorial-test', username: 'test', role } } })
    if (path === '/auth/session/refresh') return route.fulfill({ json: {
      access_token: 'isolated-browser-test', expires_at: new Date(Date.now() + 900000).toISOString(),
      user: { user_id: 'tutorial-test', username: 'test', role },
    } })
    if (path === '/orchards') return route.fulfill({ json: { orchards: [] } })
    if (path === '/weather/live' && !failures) return route.fulfill({ json: { current: {
      temperature_c: 27, humidity: 75, wind_speed_ms: 1, wind_direction_deg: 90,
      source: 'synthetic', cloud_cover_pct: 80,
    } } })
    if (path === '/simulation/runs' && !failures) return route.fulfill({ json: { runs: forecast ? [forecast] : [] } })
    if (forecast && path === `/simulation/runs/${forecast.run_id}`) return route.fulfill({ json: forecast })
    if (path === '/alerts/email/recipients') return route.fulfill({ json: role === 'admin' ? alertRecipients : [] })
    if (path === '/alerts') return route.fulfill({ json: { alerts: [] } })
    if (path === '/observations/list') return route.fulfill({ json: { observations: [] } })
    return route.fulfill({ status: 503, json: { detail: 'Isolated test: service unavailable' } })
  })
  await page.goto('/')
  await expect(page.getByRole('button', { name: /^Quick start/ })).toBeVisible()
  return requests
}

async function next(page) {
  const title = await page.locator('#workflow-tour-title').innerText()
  await page.locator('.workflow-tour-tooltip [data-action="primary"]').click()
  await expect(page.locator('#workflow-tour-title')).not.toHaveText(title)
}

async function finish(page, inspectStep = null) {
  const titles = []
  for (let count = 0; count < 55; count++) {
    await expect(page.locator('#workflow-tour-title')).toBeVisible()
    const title = await page.locator('#workflow-tour-title').innerText()
    titles.push(title)
    await inspectStep?.(title)
    const primary = page.locator('.workflow-tour-tooltip [data-action="primary"]')
    if ((await primary.textContent())?.trim() === 'Finish') {
      await primary.click()
      await expect(page.locator('.workflow-tour-tooltip')).toHaveCount(0)
      return titles
    }
    await next(page)
  }
  throw new Error('Tour did not finish')
}

function expectReadOnly(requests) {
  // Session renewal after the user's own clicks does not write account or farm records.
  expect(requests.filter(({ method, path }) => (method !== 'GET' && path !== '/auth/session/refresh') || /export|\/sync\/run/.test(path))).toEqual([])
}

async function expectTooltipInsideViewport(page) {
  const box = await page.locator('.workflow-tour-tooltip').boundingBox()
  const viewport = page.viewportSize()
  expect(box).not.toBeNull()
  expect(box.x).toBeGreaterThanOrEqual(-0.5)
  expect(box.y).toBeGreaterThanOrEqual(-0.5)
  expect(box.x + box.width).toBeLessThanOrEqual(viewport.width + 0.5)
  expect(box.y + box.height).toBeLessThanOrEqual(viewport.height + 0.5)
}

for (const pest of ['Cecid Fly', 'Fruit Fly']) {
  for (const engine of ['Grid (CA)', 'Tree Graph']) {
    test(`${pest} / ${engine}: full tour preserves inputs and makes no write requests`, async ({ page }) => {
      const forecast = verificationForecast({ pest: pest === 'Cecid Fly' ? 'cecid' : 'fruitfly', mode: engine === 'Grid (CA)' ? 'grid' : 'tree_graph' })
      const requests = await openDashboard(page, { forecast })
      await page.getByRole('button', { name: 'Maybe later' }).click()
      await page.getByRole('button', { name: 'History', exact: true }).click()
      await page.getByRole('button', { name: /Load Result/ }).click()
      await page.locator('#sidebar-tab-simulate').click()
      await page.locator('[data-tour="pest"] button', { hasText: pest }).click()
      await page.getByRole('button', { name: /Model & Neighbor Pressure/ }).click()
      await page.locator('[data-tour="engine"] button', { hasText: engine }).click()
      await page.locator('#history-source-probability').fill('0.75')
      await page.locator('#sidebar-tab-verify').click()
      await page.locator('#observation-notes').fill('Unsaved inspection draft; do not submit')
      const start = requests.length
      await page.getByRole('button', { name: 'Tutorial', exact: true }).click()
      await page.getByRole('button', { name: /^Quick start/ }).click()
      await expect(page.locator('#workflow-tour-title')).toHaveText('Welcome to MangoPoint')
      await next(page)
      await page.locator('.workflow-tour-tooltip [data-action="back"]').click()
      await expect(page.locator('#workflow-tour-title')).toHaveText('Welcome to MangoPoint')
      const titles = await finish(page)
      expect(titles).toContain('9. Read the result')
      await expect(page.locator('#sidebar-tab-verify')).toHaveAttribute('aria-selected', 'true')
      await expect(page.locator('#observation-notes')).toHaveValue('Unsaved inspection draft; do not submit')
      await expect(page.getByRole('button', { name: 'Tutorial', exact: true })).toBeFocused()
      await page.locator('#sidebar-tab-simulate').click()
      await expect(page.locator('[data-tour="pest"] .active')).toHaveText(pest)
      await expect(page.locator('[data-tour="engine"] .active')).toHaveText(engine)
      await expect(page.locator('#history-source-probability')).toHaveValue('0.75')
      expectReadOnly(requests.slice(start))
    })
  }
}

for (const viewport of [
  { label: 'desktop', width: 1440, height: 800 },
  { label: 'narrow', width: 390, height: 844 },
]) {
  test(`administrator settings tutorial stays inside the ${viewport.label} viewport`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height })
    const requests = await openDashboard(page, { role: 'admin' })
    const start = requests.length
    await page.getByRole('button', { name: /^Quick start/ }).click()
    const targetByTitle = {
      '12. Set your recovery email': 'settings-recovery-email',
      '13. Change your password': 'settings-password',
      '14. Add notification email recipients': 'settings-notification-emails',
      '15. Read and manage notifications': 'notification-list',
    }
    const titles = await finish(page, async (title) => {
      const target = targetByTitle[title]
      if (!target) return
      await expect(page.locator(`[data-tour="${target}"]`)).toBeInViewport()
      await expectTooltipInsideViewport(page)
    })
    expect(titles).toEqual(expect.arrayContaining(Object.keys(targetByTitle)))
    expectReadOnly(requests.slice(start))
  })
}

test('custom weather, keyboard, narrow layout, close, skip and replay', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const requests = await openDashboard(page)
  await page.getByRole('button', { name: 'Maybe later' }).click()
  await page.getByRole('button', { name: 'Open simulation workspace' }).click()
  await page.locator('#sidebar-tab-setup').click()
  await page.locator('[data-tour="weather-source"] button', { hasText: 'Custom Weather' }).click()
  await page.locator('.sidebar-mobile-close').click()
  const start = requests.length
  await page.getByRole('button', { name: 'Tutorial', exact: true }).click()
  await page.getByRole('button', { name: /^Cecid Fly setup/ }).click()
  await next(page)
  for (let i = 0; i < 8; i++) {
    await page.keyboard.press('Tab')
    expect(await page.locator('.workflow-tour-tooltip').evaluate((el) => el.contains(document.activeElement))).toBe(true)
  }
  const box = await page.locator('.workflow-tour-tooltip').boundingBox()
  expect(box.x).toBeGreaterThanOrEqual(0)
  expect(box.x + box.width).toBeLessThanOrEqual(391)
  await page.keyboard.press('Escape')
  await expect(page.locator('.workflow-tour-tooltip')).toHaveCount(0)
  await expect(page.locator('[inert]')).toHaveCount(0)
  await page.getByRole('button', { name: 'Tutorial', exact: true }).click()
  await page.getByRole('button', { name: /^Cecid Fly setup/ }).click()
  const titles = await finish(page)
  expect(titles).toContain('Describe the soil at Hour 0')
  await page.getByRole('button', { name: 'Tutorial', exact: true }).click()
  await page.getByRole('button', { name: /^Fruit Fly setup/ }).click()
  await page.locator('.workflow-tour-tooltip [data-action="close"]').click()
  await expect(page.locator('.workflow-tour-tooltip')).toHaveCount(0)
  await page.getByRole('button', { name: 'Tutorial', exact: true }).click()
  await page.getByRole('button', { name: /^Understand results/ }).click()
  await page.locator('.workflow-tour-tooltip [data-action="skip"]').click()
  await expect(page.locator('[inert]')).toHaveCount(0)
  expectReadOnly(requests.slice(start))
})

test('service failures, unavailable storage and missing targets cannot trap the tour', async ({ page }) => {
  const requests = await openDashboard(page, { failures: true, storageBlocked: true })
  const start = requests.length
  await page.getByRole('button', { name: /^Quick start/ }).click()
  await page.locator('[data-tour="orchard"]').evaluate((el) => el.removeAttribute('data-tour'))
  await next(page)
  await expect(page.locator('#workflow-tour-title')).toHaveText('2. Check the weather', { timeout: 12000 })
  await finish(page)
  await expect(page.getByRole('status').filter({ hasText: 'Unavailable controls were skipped' })).toBeVisible()
  expectReadOnly(requests.slice(start))
})

test('first-use dismissal survives reload, manual replay remains available and logout cleans up', async ({ page }) => {
  await openDashboard(page)
  await page.getByRole('button', { name: 'Maybe later' }).click()
  await page.reload()
  await expect(page.getByRole('button', { name: 'Tutorial', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: /^Quick start/ })).toHaveCount(0)
  await page.getByRole('button', { name: 'Tutorial', exact: true }).click()
  await page.getByRole('button', { name: /^Understand results/ }).click()
  await page.locator('.workflow-tour-tooltip [data-action="skip"]').click()
  await page.getByRole('button', { name: 'Logout' }).click()
  await expect(page.locator('.workflow-tour-tooltip')).toHaveCount(0)
  await expect(page.locator('[inert]')).toHaveCount(0)
})
