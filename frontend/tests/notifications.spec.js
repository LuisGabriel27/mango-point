import { expect, test } from '@playwright/test'

test.use({ timezoneId: 'UTC' })

function notification(index) {
  return {
    alert_id: `notification-check-${index}`,
    orchard_id: 'default-orchard',
    status: 'active',
    severity: 'high',
    triggered_at: '2026-10-13T05:00:00Z',
    message: `Isolated notification ${index}`,
    recommended_actions: [],
  }
}

// All API responses are isolated fixtures; no alerts or emails reach the backend.
async function openNotifications(page) {
  const state = { alerts: [1, 2, 3, 4].map(notification), unavailable: false, requests: [] }
  await page.clock.install({ time: new Date('2026-10-13T05:00:00Z') })
  await page.addInitScript(() => sessionStorage.setItem('access_token', 'isolated-notification-check'))
  await page.route(/\/(auth|orchards|weather|monitoring|simulation|observations|alerts|sync|evaluation|validation)(\/|\?|$)/, async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    state.requests.push({ method: request.method(), path })
    if (path === '/auth/me') return route.fulfill({ json: { user: { user_id: 'notification-check', username: 'test', role: 'scout' } } })
    if (path === '/orchards') return route.fulfill({ json: { orchards: [] } })
    if (path === '/simulation/runs') return route.fulfill({ json: { runs: [] } })
    if (path === '/weather/live') return route.fulfill({ json: { current: { temperature_c: 27, source: 'synthetic' } } })
    if (path === '/alerts' && !state.unavailable) return route.fulfill({ json: { alerts: state.alerts } })
    return route.fulfill({ status: 503, json: { detail: 'Notifications are temporarily unavailable.' } })
  })
  await page.goto('/')
  await page.getByRole('button', { name: 'Maybe later' }).click()
  await expect(page.locator('.navbar-bell-badge')).toHaveText('4')
  return state
}

test('four waiting notifications do not prevent a fifth from appearing automatically', async ({ page }) => {
  const state = await openNotifications(page)
  state.alerts.push(notification(5))
  await page.clock.fastForward(61_000)
  await expect(page.locator('.navbar-bell-badge')).toHaveText('5')
  await page.getByRole('button', { name: 'Notifications', exact: true }).click()
  await expect(page.locator('.navbar-bell-list')).toContainText('Isolated notification 5')

  state.alerts.push(notification(6))
  await page.getByRole('button', { name: 'Notifications', exact: true }).click()
  await page.getByRole('button', { name: 'Notifications', exact: true }).click()
  await expect(page.locator('.navbar-bell-badge')).toHaveText('6')
  expect(state.requests.filter(({ method }) => method !== 'GET')).toEqual([])
})

test('failed notification refresh retains waiting alerts and provides a working retry', async ({ page }) => {
  const state = await openNotifications(page)
  await page.getByRole('button', { name: 'Notifications', exact: true }).click()
  await expect(page.locator('.navbar-bell-list')).toContainText('Isolated notification 4')
  state.unavailable = true
  await page.clock.fastForward(61_000)
  const error = page.locator('.navbar-bell-list [role="alert"]')
  await expect(error).toContainText('Notifications are temporarily unavailable.')
  await expect(page.locator('.navbar-bell-badge')).toHaveText('4')
  await expect(page.locator('.navbar-bell-list')).toContainText('Isolated notification 4')

  state.unavailable = false
  state.alerts.push(notification(5))
  await error.getByRole('button', { name: 'Retry' }).click()
  await expect(error).toHaveCount(0)
  await expect(page.locator('.navbar-bell-badge')).toHaveText('5')
  expect(state.requests.filter(({ method }) => method !== 'GET')).toEqual([])
})

test('unresolved notifications retain their full Philippine date across days and narrow layouts', async ({ page }, testInfo) => {
  const state = await openNotifications(page)
  state.alerts[0] = {
    ...state.alerts[0],
    triggered_at: '2026-10-06T18:48:00Z',
    email_sent: true,
    zone_name: 'Fruit fly weather forecast',
  }
  await expect(page.getByRole('button', { name: 'Guide', exact: true })).toBeVisible()
  await expect(page.locator('.navbar-clock')).toHaveCount(0)
  await page.getByRole('button', { name: 'Notifications', exact: true }).click()
  const timestamp = page.locator('.notification-timestamp').first()
  await expect(timestamp).toContainText('Oct 7, 2026')
  await expect(timestamp).toContainText('2:48 AM PHT')
  await expect(timestamp).toHaveAttribute('datetime', '2026-10-06T18:48:00.000Z')
  await page.clock.fastForward(2 * 24 * 60 * 60 * 1000)
  await expect(timestamp).toContainText('Oct 7, 2026')

  for (const width of [390, 320]) {
    await page.setViewportSize({ width, height: 844 })
    await expect(timestamp).toBeVisible()
    const box = await timestamp.boundingBox()
    expect(box.x).toBeGreaterThanOrEqual(0)
    expect(box.x + box.width).toBeLessThanOrEqual(width)
    await page.screenshot({ path: testInfo.outputPath(`notification-date-${width}.png`) })
  }
  expect(state.requests.filter(({ method }) => method !== 'GET')).toEqual([])
})
