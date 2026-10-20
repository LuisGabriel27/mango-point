import { expect, test } from '@playwright/test'

// Isolated browser/API fixtures. No real sign-in email, simulation or farm
// record is created. Different hosts deliberately reject each other's token.
async function sessionServer(page, issuingMode = 'local') {
  await page.clock.install({ time: new Date('2026-10-20T00:00:00Z') })
  await page.clock.pauseAt(new Date('2026-10-20T00:00:01Z'))
  const state = { local: issuingMode === 'local', unavailable: false, outageStatus: null,
    revoked: false, rejectionStatus: 401, requests: [], checks: 0 }
  const user = { user_id: 7, username: 'offline-session', full_name: 'Offline Session', role: 'operator' }
  const issuingHost = issuingMode === 'local' ? '127.0.0.1:8000' : '127.0.0.1:3011'
  await page.route(/arcgisonline|tile.openstreetmap|demotiles.maplibre/, (route) => route.abort())
  await page.route(/\/(health|auth|orchards|weather|monitoring|simulation|observations|alerts|sync|evaluation|validation)(\/|\?|$)/, async (route) => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname
    if (path === '/health') return state.local
      ? route.fulfill({ json: { status: 'healthy', database: 'connected' } }) : route.abort()
    state.requests.push({ host: url.host, path, method: request.method() })
    if (state.unavailable) return state.outageStatus
      ? route.fulfill({ status: state.outageStatus, json: { detail: 'Temporary test outage' } }) : route.abort()
    if (path === '/auth/login') return route.fulfill({ json: {
      verification_required: true, challenge_id: '00000000-0000-0000-0000-000000000001',
      masked_email: 'o***@example.test', resend_after_seconds: 60,
      expires_at: new Date(await page.evaluate(() => Date.now()) + 300000).toISOString(),
    } })
    if (path === '/auth/login/verify' || path === '/auth/session/refresh') {
      if (path === '/auth/session/refresh') state.checks++
      return route.fulfill({ json: {
        access_token: 'isolated-offline-session', user,
        expires_at: new Date(await page.evaluate(() => Date.now()) + 900000).toISOString(),
      } })
    }
    if (state.revoked || url.host !== issuingHost) return route.fulfill({ status: state.rejectionStatus,
      json: { detail: 'Session ended. Please sign in again.' } })
    if (path === '/auth/me') { state.checks++; return route.fulfill({ json: { user } }) }
    if (path === '/auth/logout') return route.fulfill({ json: { message: 'Logged out.' } })
    if (request.method() !== 'GET') return route.fulfill({ status: 400, json: { detail: 'Unexpected fixture write' } })
    if (path === '/orchards') return route.fulfill({ json: { orchards: [] } })
    if (path === '/simulation/runs') return route.fulfill({ json: { runs: [] } })
    if (path === '/alerts') return route.fulfill({ json: { alerts: [] } })
    return route.fulfill({ status: 503, json: { detail: 'Isolated test service unavailable' } })
  })
  await page.goto('/login')
  await page.getByLabel('Username or email').fill('offline-session')
  await page.getByLabel('Password', { exact: true }).fill('isolated-password')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page.getByRole('textbox', { name: 'Digit 1 of 6', exact: true }).fill('123456')
  await expect(page.getByRole('button', { name: 'Logout', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Maybe later', exact: true }).click()
  const close = page.getByRole('button', { name: 'Close connection status', exact: true })
  if (await close.isVisible()) await close.click()
  return { state, issuingHost }
}

async function sessionSnapshot(page) {
  return page.evaluate(() => Object.fromEntries([
    'access_token', 'mangopoint.session.apiTarget', 'mangopoint.session.user',
    'mangopoint.session.lastActivity', 'mangopoint.session.expiresAt',
  ].map((key) => [key, sessionStorage.getItem(key)])))
}

for (const mode of ['local', 'remote']) {
  test(`${mode} session survives disconnection and reconnection without switching APIs or losing drafts`, async ({ page, context }) => {
    const { state, issuingHost } = await sessionServer(page, mode)
    await page.locator('#sidebar-tab-simulate').click()
    await page.locator('#days-flowering').fill('75')
    const token = (await sessionSnapshot(page)).access_token
    state.unavailable = true
    // An available companion must not receive a remote session on reconnect.
    state.local = mode === 'remote'
    await context.setOffline(true)
    await page.clock.fastForward(31000)
    await expect(page.getByRole('button', { name: 'Logout', exact: true })).toBeVisible()
    state.unavailable = false
    const before = state.checks
    await context.setOffline(false)
    await expect.poll(() => state.checks).toBeGreaterThan(before)
    await expect(page.locator('#days-flowering')).toHaveValue('75')
    await expect(page.locator('.navbar-username')).toHaveText('Offline Session')
    expect((await sessionSnapshot(page)).access_token).toBe(token)
    expect(new Set(state.requests.map((request) => request.host))).toEqual(new Set([issuingHost]))
    expect(state.requests.filter((request) => request.method !== 'GET'
      && !['/auth/login', '/auth/login/verify', '/auth/session/refresh'].includes(request.path))).toEqual([])
  })
}

for (const status of [null, 502, 503, 504]) {
  test(`reloading during ${status ?? 'network'} failure preserves the verified user and original deadlines`, async ({ page }) => {
    const { state, issuingHost } = await sessionServer(page)
    const saved = await sessionSnapshot(page)
    state.unavailable = true
    state.outageStatus = status
    state.local = false
    await page.reload()
    await expect(page.getByRole('button', { name: 'Logout', exact: true })).toBeVisible()
    await expect(page.locator('.navbar-username')).toHaveText('Offline Session')
    expect(await sessionSnapshot(page)).toEqual(saved)
    state.unavailable = false
    const before = state.checks
    await page.evaluate(() => window.dispatchEvent(new Event('online')))
    await expect.poll(() => state.checks).toBeGreaterThan(before)
    expect(new Set(state.requests.map((request) => request.host))).toEqual(new Set([issuingHost]))
  })
}

for (const status of [401, 403]) {
  test(`a rejected session (${status}) is cleared when its issuing API returns after an outage`, async ({ page }) => {
    const { state } = await sessionServer(page)
    state.unavailable = true
    await page.reload()
    await expect(page.getByRole('button', { name: 'Logout', exact: true })).toBeVisible()
    state.unavailable = false
    state.revoked = true
    state.rejectionStatus = status
    await page.evaluate(() => window.dispatchEvent(new Event('online')))
    await expect(page.locator('#login-identifier')).toBeVisible()
    await expect(page.getByRole('status').filter({ hasText: 'Session ended' })).toBeVisible()
    expect(Object.values(await sessionSnapshot(page))).toEqual([null, null, null, null, null])
  })
}

test('logging out during an outage clears the session and cannot be reversed by reconnection', async ({ page }) => {
  const { state, issuingHost } = await sessionServer(page, 'remote')
  state.unavailable = true
  state.local = true
  await page.evaluate(() => window.dispatchEvent(new Event('online')))
  await page.getByRole('button', { name: 'Logout', exact: true }).click()
  await page.getByRole('alertdialog').getByRole('button', { name: 'Log out', exact: true }).click()
  await expect(page.locator('#login-identifier')).toBeVisible()
  await expect.poll(() => state.requests.filter((request) => request.path === '/auth/logout').length).toBe(1)
  expect(state.requests.find((request) => request.path === '/auth/logout').host).toBe(issuingHost)
  state.unavailable = false
  await page.evaluate(() => window.dispatchEvent(new Event('online')))
  await page.clock.fastForward(31000)
  await expect(page.locator('#login-identifier')).toBeVisible()
  expect(Object.values(await sessionSnapshot(page))).toEqual([null, null, null, null, null])
})

test('a focus event immediately after sign-out cannot recreate cleared session metadata', async ({ page }) => {
  await sessionServer(page)
  await page.evaluate(async () => {
    const { SESSION_INVALID_EVENT } = await import('/src/utils/sessionMonitor.js')
    window.dispatchEvent(new CustomEvent(SESSION_INVALID_EVENT, { detail: {
      token: sessionStorage.getItem('access_token'), message: 'Session replaced by recovery.',
    } }))
    // Dispatch in the same task, before React can run effect cleanup.
    window.dispatchEvent(new Event('focus'))
  })
  await expect(page.locator('#login-identifier')).toBeVisible()
  expect(Object.values(await sessionSnapshot(page))).toEqual([null, null, null, null, null])
})
