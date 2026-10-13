import { expect, test } from '@playwright/test'

test.use({ actionTimeout: 10000 })

// Isolated browser fixtures: never sent to the backend or saved as farm evidence.
async function openDashboard(page) {
  const writes = []
  await page.addInitScript(() => sessionStorage.setItem('access_token', 'isolated-browser-test'))
  await page.route(/\/(auth|orchards|weather|monitoring|simulation|observations|alerts|sync|evaluation|validation)(\/|\?|$)/, async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (request.method() !== 'GET') writes.push({ method: request.method(), path })
    if (path === '/auth/me') return route.fulfill({ json: { user: { user_id: 'zone-editor-test', username: 'test', role: 'scout' } } })
    if (path === '/orchards') return route.fulfill({ json: { orchards: [] } })
    if (path === '/weather/live') return route.fulfill({ json: { current: {
      temperature_c: 27, humidity: 75, wind_speed_ms: 1, wind_direction_deg: 90,
      source: 'synthetic', cloud_cover_pct: 80,
    } } })
    if (path === '/simulation/runs') return route.fulfill({ json: { runs: [] } })
    if (path === '/alerts') return route.fulfill({ json: { alerts: [] } })
    if (path === '/observations/list') return route.fulfill({ json: { observations: [] } })
    return route.fulfill({ status: 503, json: { detail: 'Isolated test: service unavailable' } })
  })
  await page.goto('/')
  await page.getByRole('button', { name: 'Maybe later' }).click()
  await expect(page.locator('.maplibregl-canvas')).toBeVisible()
  return writes
}

async function choose(panel, label, option) {
  const field = panel.locator('label').filter({ has: panel.page().locator('span', { hasText: new RegExp(`^${label}$`) }) })
  await field.getByRole('combobox').click()
  await field.getByRole('option', { name: option, exact: true }).click()
}

async function canvasBox(page) {
  const box = await page.locator('.maplibregl-canvas').boundingBox()
  expect(box).not.toBeNull()
  return box
}

for (const viewport of [
  { label: 'desktop', width: 1440, height: 960 },
  { label: 'narrow', width: 390, height: 844 },
]) {
  test(`zone editor collapses on outside clicks, preserves settings and allows navigation on ${viewport.label}`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height })
    const writes = await openDashboard(page)
    const toggle = page.locator('[data-tour="map-zones"]')
    const panel = page.locator('#map-zone-editor-panel')
    await toggle.click()
    await choose(panel, 'Zone type', 'Management')
    await panel.getByRole('textbox').fill('Unsaved area draft')
    await expect(panel).toBeVisible()

    const box = await canvasBox(page)
    await page.mouse.click(box.x + box.width - 18, box.y + box.height * 0.7)
    await expect(panel).toHaveCount(0)
    await expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await toggle.click()
    await expect(panel.getByRole('textbox')).toHaveValue('Unsaved area draft')
    // Clicking the launcher still toggles once, rather than reopening after dismissal.
    await toggle.click()
    await expect(panel).toHaveCount(0)
    await toggle.click()
    const grid = page.getByRole('button', { name: /Grid$/ })
    await grid.click()
    await expect(panel).toHaveCount(0)
    await expect(grid).toHaveAttribute('aria-pressed', 'true')

    await toggle.click()
    await page.getByRole('button', { name: /Layers$/ }).click()
    await expect(panel).toHaveCount(0)
    await expect(page.locator('#map-layers-popover')).toBeVisible()
    await toggle.click()
    await expect(panel).toBeVisible()
    await panel.getByRole('button', { name: /Manage/ }).click()
    await expect(panel).toHaveCount(0)
    await expect(page.locator('#map-zone-manager')).toBeVisible()
    await toggle.click()
    await expect(panel).toBeVisible()

    if (viewport.label === 'narrow') {
      await page.getByRole('button', { name: 'Open simulation workspace' }).click()
      await expect(panel).toHaveCount(0)
      await expect(page.locator('.floating-right-sidebar')).toHaveClass(/is-mobile-open/)
      await page.locator('.sidebar-mobile-close').click()
    } else {
      await page.locator('#sidebar-tab-verify').click()
      await expect(panel).toHaveCount(0)
      await expect(page.locator('#sidebar-tab-verify')).toHaveAttribute('aria-selected', 'true')
    }
    await toggle.click()
    await page.screenshot({ path: testInfo.outputPath('zone-editor-open.png') })
    if (viewport.label === 'desktop') {
      await page.getByRole('button', { name: 'History', exact: true }).click()
      await expect(panel).toHaveCount(0)
      await page.getByRole('button', { name: 'Live Map', exact: true }).click()
      await expect(panel).toHaveCount(0)
    } else {
      await page.getByRole('button', { name: 'Open settings' }).click()
      await expect(panel).toHaveCount(0)
      await expect(page.getByRole('dialog', { name: 'Settings', exact: true })).toBeVisible()
      await page.getByRole('button', { name: 'Close settings' }).click()
      await expect(panel).toHaveCount(0)
    }
    await page.screenshot({ path: testInfo.outputPath('zone-editor-collapsed.png') })
    expect(writes).toEqual([])
  })

  test(`zone drawing survives map gestures and outside collapse on ${viewport.label}`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height })
    const writes = await openDashboard(page)
    const toggle = page.locator('[data-tour="map-zones"]')
    const panel = page.locator('#map-zone-editor-panel')
    await toggle.click()
    await choose(panel, 'Drawing method', 'Point polygon')
    for (const zoneType of ['Stage', 'Status', 'Management', 'Weed Habitat']) {
      await choose(panel, 'Zone type', zoneType)
      await panel.getByRole('button', { name: /Start drawing/ }).click()
      const box = await canvasBox(page)
      await page.mouse.click(box.x + box.width - 18, box.y + box.height * 0.6)
      await expect(panel).toHaveClass(/is-drawing/)
      await expect(panel.getByRole('button', { name: /Undo point/ })).toBeEnabled()
      await page.getByRole('button', { name: /Grid$/ }).click()
      await expect(panel).toHaveCount(0)
      await toggle.click()
      await expect(panel).toHaveClass(/is-drawing/)
      await panel.getByRole('button', { name: /Undo point/ }).click()
      await expect(panel.getByRole('button', { name: /Undo point/ })).toBeDisabled()
      await panel.getByRole('button', { name: 'Cancel', exact: true }).click()
    }

    await choose(panel, 'Drawing method', 'Freehand lasso')
    await panel.getByRole('button', { name: /Start drawing/ }).click()
    const box = await canvasBox(page)
    const x = box.x + box.width - 70
    const y = box.y + box.height * 0.5
    await page.mouse.move(x, y)
    await page.mouse.down()
    await page.mouse.move(x + 40, y, { steps: 4 })
    await page.mouse.move(x + 40, y + 80, { steps: 4 })
    await page.mouse.move(x, y + 80, { steps: 4 })
    await page.mouse.up()
    await expect(panel).toHaveClass(/is-drawing/)
    await expect(panel.getByRole('button', { name: /Undo point/ })).toBeEnabled()
    await panel.getByRole('button', { name: 'Cancel', exact: true }).click()
    expect(writes).toEqual([])
  })
}
