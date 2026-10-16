import { expect, test } from '@playwright/test'

test.use({ actionTimeout: 10000 })

// Isolated UI fixtures: help interactions must never submit a forecast or farm edit.
async function openControls(page) {
  const writes = []
  await page.addInitScript(() => sessionStorage.setItem('access_token', 'isolated-control-help-test'))
  await page.route(/\/(auth|orchards|weather|monitoring|simulation|observations|alerts|sync|evaluation|validation)(\/|\?|$)/, async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (request.method() !== 'GET') writes.push({ method: request.method(), path })
    if (path === '/auth/me') return route.fulfill({ json: { user: { user_id: 'control-help-test', username: 'test', role: 'scout' } } })
    if (path === '/orchards') return route.fulfill({ json: { orchards: [] } })
    if (path === '/weather/live') return route.fulfill({ json: { current: {
      temperature_c: 27, humidity: 75, wind_speed_ms: 1, wind_direction_deg: 90,
      source: 'open-meteo', cloud_cover_pct: 80,
    } } })
    if (path === '/simulation/runs') return route.fulfill({ json: { runs: [] } })
    if (path === '/alerts') return route.fulfill({ json: { alerts: [] } })
    if (path === '/observations/list') return route.fulfill({ json: { observations: [] } })
    return route.fulfill({ status: 503, json: { detail: 'Isolated UI test' } })
  })
  await page.goto('/')
  await page.getByRole('button', { name: 'Maybe later' }).click()
  if (page.viewportSize().width < 768) {
    await page.getByRole('button', { name: 'Open simulation workspace' }).click()
  }
  await page.locator('#sidebar-tab-setup').click()
  return writes
}

async function expectInsideViewport(page) {
  const box = await page.getByRole('tooltip').boundingBox()
  const viewport = page.viewportSize()
  expect(box).not.toBeNull()
  expect(box.x).toBeGreaterThanOrEqual(11)
  expect(box.y).toBeGreaterThanOrEqual(11)
  expect(box.x + box.width).toBeLessThanOrEqual(viewport.width - 11)
  expect(box.y + box.height).toBeLessThanOrEqual(viewport.height - 11)
  // This also checks that a portal is above the mobile panel or weather dialog.
  await page.getByRole('tooltip').hover()
}

async function inspectHelp(page, label, text) {
  const help = page.getByRole('button', { name: `Help: ${label}`, exact: true })
  await help.hover()
  await expect(page.getByRole('tooltip')).toContainText(text)
  await expect(help).toHaveAttribute('aria-describedby', await page.getByRole('tooltip').getAttribute('id'))
  await expectInsideViewport(page)
  await page.keyboard.press('Escape')
  await expect(page.getByRole('tooltip')).toHaveCount(0)
  await page.mouse.move(0, 0)
}

test('help supports hover, moving onto the text, keyboard focus, Escape and click dismissal', async ({ page }) => {
  const writes = await openControls(page)
  const help = page.getByRole('button', { name: 'Help: Current monitoring stage', exact: true })
  await expect(page.getByRole('tooltip')).toHaveCount(0)
  await expect(page.getByText('Cecid live alerts require Fruitlets;', { exact: false })).toHaveCount(0)
  await help.hover()
  await expect(page.getByRole('tooltip')).toContainText('Cecid live alerts require Fruitlets')
  await page.getByRole('tooltip').hover()
  await expect(page.getByRole('tooltip')).toBeVisible()
  await page.mouse.move(0, 0)
  await expect(page.getByRole('tooltip')).toHaveCount(0)

  await help.focus()
  await expect(page.getByRole('tooltip')).toBeVisible()
  await help.press('Escape')
  await expect(page.getByRole('tooltip')).toHaveCount(0)
  await expect(help).toBeFocused()
  await help.press('Tab')
  await page.keyboard.press('Shift+Tab')
  await expect(help).toBeFocused()
  await expect(page.getByRole('tooltip')).toBeVisible()
  await help.press('Tab')
  await expect(page.getByRole('tooltip')).toHaveCount(0)

  await help.click()
  await expect(page.getByRole('tooltip')).toBeVisible()
  await help.click()
  await expect(page.getByRole('tooltip')).toHaveCount(0)
  await help.click()
  await page.locator('#sidebar-tab-setup').focus()
  await expect(page.getByRole('tooltip')).toHaveCount(0)
  await help.click()
  await page.getByRole('button', { name: 'Help: Live weather', exact: true }).hover()
  await expect(page.getByRole('tooltip')).toHaveCount(1)
  await expect(page.getByRole('tooltip')).toContainText('forecast estimates')
  expect(writes).toEqual([])
})

for (const pest of ['Cecid Fly', 'Fruit Fly']) {
  for (const width of [1440, 390]) {
    test(`${pest}: control help stays within ${width}px viewport and preserves inputs`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: 844 })
      const writes = await openControls(page)
      await page.locator('#sidebar-tab-simulate').click()
      await page.locator('[data-tour="pest"] button', { hasText: pest }).click()
      await inspectHelp(page, 'Orchard Stage', 'Fruitlets are susceptible to Cecid Fly')
      await inspectHelp(page, 'Days Since Flowering', 'Higher = riper fruit')
      await expect(page.locator('#days-flowering')).toHaveValue('60')
      await page.getByRole('button', { name: /Model & Neighbor Pressure/ }).click()
      for (const engine of ['Grid (CA)', 'Tree Graph']) {
        await page.locator('[data-tour="engine"] button', { hasText: engine }).click()
        if (engine === 'Tree Graph') await inspectHelp(page, 'Spread Model', 'crown-to-crown distances')
        else if (pest === 'Cecid Fly') await inspectHelp(page, 'Spread Model', '1–3 soil anchors')
        else await expect(page.getByRole('button', { name: 'Help: Spread Model', exact: true })).toHaveCount(0)
      }
      await inspectHelp(page, 'Repeated Runs', 'Across runs shows how often infestation is present')
      await page.getByRole('button', { name: 'Help: Repeated Runs', exact: true }).hover()
      if (pest === 'Fruit Fly') await expect(page.getByRole('tooltip')).toContainText('Newly infested fruit does not create more adult sources')
      else await expect(page.getByRole('tooltip')).not.toContainText('Fruit Fly pressure')
      await page.keyboard.press('Escape')
      await page.locator('#history-source-probability').fill('0.75')
      await inspectHelp(page, 'Default Source Presence', 'not field-calibrated probabilities')
      await expect(page.locator('#history-source-probability')).toHaveValue('0.75')
      await inspectHelp(page, 'Neighbor Pressure', pest === 'Cecid Fly' ? 'outside adult exposure' : 'unmanaged orchards')
      await expect(page.getByText('No outside neighbor pressure included.', { exact: true })).toBeVisible()

      await page.getByRole('button', { name: 'Help: Default Source Presence', exact: true }).hover()
      await page.screenshot({ path: testInfo.outputPath('source-presence-help.png') })
      await page.locator('.sidebar-workflow-panels').evaluate((element) => {
        element.scrollTop = element.scrollTop > 0 ? 0 : 30
      })
      await expect(page.getByRole('tooltip')).toHaveCount(0)
      await expect(page.locator('#history-source-probability')).toHaveValue('0.75')
      expect(writes).toEqual([])
    })
  }
}

test('treatment and accuracy help reflects selected settings without activating controls', async ({ page }) => {
  const writes = await openControls(page)
  await page.locator('#sidebar-tab-simulate').click()
  await page.getByRole('button', { name: /Treatment Scenario/ }).click()
  await page.locator('#treatment-enabled').check()
  for (const [type, description] of [
    ['Protective', 'Source output is unchanged'],
    ['Targeted', 'including active historical reservoirs'],
    ['Sanitation', 'Incoming susceptibility is unchanged'],
    ['Combined', 'reduces incoming infestation pressure and source output'],
  ]) {
    await page.getByRole('button', { name: type, exact: true }).click()
    await inspectHelp(page, 'Treatment type', description)
    await expect(page.locator('#treatment-efficacy')).toHaveValue('0.65')
  }
  await page.getByRole('button', { name: /Accuracy Settings/ }).click()
  await inspectHelp(page, 'Start from field observations', 'Uses scout reports')
  await expect(page.locator('#obs-seeds')).not.toBeChecked()
  await inspectHelp(page, 'Cautious sensitivity', 'strong trigger conditions')
  await expect(page.getByRole('button', { name: 'Standard', exact: true })).toHaveClass(/btn-primary/)
  expect(writes).toEqual([])
})

test('weather help is available inside the editor and Escape dismisses help before the dialog', async ({ page }) => {
  const writes = await openControls(page)
  await inspectHelp(page, 'Live weather', 'forecast estimates')
  await page.locator('[data-tour="weather-source"] button').filter({ hasText: 'Custom Weather' }).click()
  await inspectHelp(page, 'Start date & time', 'Guimaras time')
  await page.getByText('Soil & Cecid test preset', { exact: true }).click()
  await inspectHelp(page, 'Starting soil', 'No rainfall in the 72 hours')
  await page.getByRole('button', { name: 'Moist now', exact: true }).click()
  await inspectHelp(page, 'Starting soil', 'not a measured soil-water percentage')
  await inspectHelp(page, 'Dawn + dusk test', 'Loading it selects Cecid Fly and a 7-day simulation')
  await page.getByRole('button', { name: /Edit periods$/ }).click()
  await page.getByRole('button', { name: /Set up periods$/ }).click()
  await inspectHelp(page, 'Daylight light condition', 'Tree-canopy shade alone does not enable Cecid')
  await expect(page.getByRole('dialog', { name: 'Set up weather periods', exact: true })).toBeVisible()
  expect(writes).toEqual([])
})

test.describe('touch controls', () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true })
  test('tap opens help and a second tap or outside tap dismisses it', async ({ page }) => {
    const writes = await openControls(page)
    const help = page.getByRole('button', { name: 'Help: Current monitoring stage', exact: true })
    await help.tap()
    await expect(page.getByRole('tooltip')).toBeVisible()
    await expectInsideViewport(page)
    await help.tap()
    await expect(page.getByRole('tooltip')).toHaveCount(0)
    await help.tap()
    await page.locator('#sidebar-panel-setup .sidebar-section-title').filter({ hasText: /^Orchard$/ }).tap()
    await expect(page.getByRole('tooltip')).toHaveCount(0)
    expect(writes).toEqual([])
  })
})
