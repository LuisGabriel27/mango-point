import { expect, test } from '@playwright/test'

test.use({ actionTimeout: 10000 })

// Isolated browser fixtures: no requests reach the application backend.
async function openCustomWeather(page, pest) {
  const writes = []
  await page.addInitScript(() => sessionStorage.setItem('access_token', 'isolated-browser-test'))
  await page.route(/\/(auth|orchards|weather|monitoring|simulation|observations|alerts|sync|evaluation|validation)(\/|\?|$)/, async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (request.method() !== 'GET') writes.push({ method: request.method(), path })
    if (path === '/auth/me') return route.fulfill({ json: { user: { user_id: 'weather-review-test', username: 'test', role: 'scout' } } })
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
  if (page.viewportSize().width < 768) {
    await page.getByRole('button', { name: 'Open simulation workspace' }).click()
  }
  await page.locator('#sidebar-tab-simulate').click()
  await page.locator('[data-tour="pest"] button', { hasText: pest }).click()
  await page.locator('#sidebar-tab-setup').click()
  await page.locator('[data-tour="weather-source"] button', { hasText: 'Custom Weather' }).click()
  return writes
}

for (const pest of ['Cecid Fly', 'Fruit Fly']) {
  for (const viewport of [
    { label: 'desktop', width: 1440, height: 960 },
    { label: 'narrow', width: 390, height: 844 },
  ]) {
    test(`${pest}: weather schedule review opens by pointer and keyboard on ${viewport.label}`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      const writes = await openCustomWeather(page, pest)
      const review = page.getByRole('button', { name: 'Review weather periods' })
      const details = page.getByRole('dialog', { name: 'Weather period details' })
      const editor = page.getByRole('dialog', { name: 'Set up weather periods' })

      // The arrow and the rest of the card share the same click target.
      await review.locator('.weather-period-general-preview-arrow').click()
      await expect(details).toBeVisible()
      await expect(details.getByRole('list', { name: 'Custom weather periods' })).toBeVisible()
      await expect(details.locator('input')).toHaveCount(0)
      await details.getByRole('button', { name: 'Set up periods' }).click()
      await editor.getByRole('spinbutton', { name: /^Temperature/ }).fill('31')
      await editor.getByRole('button', { name: 'Done', exact: true }).click()

      for (const key of ['Enter', 'Space']) {
        await review.focus()
        await review.press(key)
        await expect(details).toBeVisible()
        await expect(details.getByRole('list')).toContainText('31°C')
        await expect(review).toHaveAttribute('aria-expanded', 'true')
        await page.keyboard.press('Escape')
        await expect(details).toHaveCount(0)
        await expect(review).toHaveAttribute('aria-expanded', 'false')
        if (viewport.label === 'narrow') {
          await expect(page.locator('.floating-right-sidebar')).toHaveClass(/is-mobile-open/)
        }
      }

      await review.click()
      const box = await details.boundingBox()
      expect(box.x).toBeGreaterThanOrEqual(0)
      expect(box.x + box.width).toBeLessThanOrEqual(viewport.width)
      await page.screenshot({ path: testInfo.outputPath('weather-period-review.png') })
      await details.getByRole('button', { name: 'Close weather periods' }).click()
      await page.getByRole('button', { name: /Edit periods$/ }).click()
      await details.getByRole('button', { name: 'Set up periods' }).click()
      await expect(editor.getByRole('spinbutton', { name: /^Temperature/ })).toHaveValue('31')
      await editor.getByRole('button', { name: 'Done', exact: true }).click()
      expect(writes).toEqual([])
    })
  }
}
