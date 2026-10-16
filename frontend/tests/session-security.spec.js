import { test, expect } from '@playwright/test'

// Isolated accounts and API responses. Nothing is sent to the real server.
function server() {
  let version = 1, sequence = 0, password = 'old-password'
  const tokens = new Map(), refreshes = []
  const user = { user_id: 7, username: 'session-test', full_name: 'Session Test', role: 'operator' }
  let heldRefresh = null
  return { refreshes,
    holdRefresh(handler) { heldRefresh = handler },
    async connect(page) {
      await page.clock.install()
      await page.route(/\/(auth|orchards|weather|monitoring|simulation|observations|alerts|sync|evaluation|validation)(\/|\?|$)/, async (route) => {
        const request = route.request(), path = new URL(request.url()).pathname
        const body = request.method() === 'POST' ? request.postDataJSON() : null
        const token = request.headers().authorization?.replace(/^Bearer /, '')
        const valid = token && tokens.get(token) === version
        const issue = async (age = 0) => {
          const issued = `isolated-session-${version}-${++sequence}`
          tokens.set(issued, version)
          const now = await page.evaluate(() => Date.now())
          return { access_token: issued, expires_at: new Date(now + (900 - age) * 1000).toISOString(), user }
        }
        if (path === '/auth/login') {
          return body.password === password
            ? route.fulfill({ json: await issue() })
            : route.fulfill({ status: 401, json: { detail: 'Invalid credentials.' } })
        }
        if (path.startsWith('/auth/') && !valid) return route.fulfill({ status: 401,
          json: { detail: 'Your password changed or your session was revoked. Please sign in again.' } })
        if (path === '/auth/me') return route.fulfill({ json: { user } })
        if (path === '/auth/logout') return route.fulfill({ json: { message: 'Logged out.' } })
        if (path === '/auth/session/refresh') {
          refreshes.push(body)
          const response = await issue(body.activity_age_seconds)
          if (heldRefresh) return heldRefresh(route, response)
          return route.fulfill({ json: response })
        }
        if (path === '/auth/password') {
          if (body.current_password !== password) return route.fulfill({ status: 400, json: { detail: 'Current password is incorrect.' } })
          password = body.new_password
          version++
          return route.fulfill({ json: { message: 'Password updated. All devices must sign in again.' } })
        }
        if (request.method() !== 'GET') return route.fulfill({ status: 400, json: { detail: 'Unexpected test write.' } })
        if (path === '/orchards') return route.fulfill({ json: { orchards: [] } })
        if (path === '/simulation/runs') return route.fulfill({ json: { runs: [] } })
        if (path === '/alerts') return route.fulfill({ json: { alerts: [] } })
        return route.fulfill({ status: 503, json: { detail: 'Isolated test: service unavailable.' } })
      })
    },
  }
}

async function signIn(page, password = 'old-password') {
  await page.goto('/login')
  await page.locator('#login-identifier').fill('session-test')
  await page.locator('#login-password').fill(password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Logout', exact: true })).toBeVisible()
  const invitation = page.getByRole('button', { name: 'Maybe later', exact: true })
  if (await invitation.isVisible()) await invitation.click()
}

test('background polling does not prevent logout after fifteen minutes of inactivity', async ({ page }) => {
  const api = server()
  await api.connect(page)
  await signIn(page)
  await page.clock.fastForward(15 * 60 * 1000 + 100)
  await expect(page.locator('#login-identifier')).toBeVisible()
  await expect(page.getByRole('status').filter({ hasText: '15 minutes of inactivity' })).toBeVisible()
  expect(await page.evaluate(() => sessionStorage.getItem('access_token'))).toBeNull()
  expect(api.refreshes).toHaveLength(0)
})

test('real interaction renews the session, while reloading preserves its inactivity deadline', async ({ page }) => {
  const api = server()
  await api.connect(page)
  await signIn(page)
  const originalToken = await page.evaluate(() => sessionStorage.getItem('access_token'))
  await page.clock.fastForward(14 * 60 * 1000)
  await page.getByRole('button', { name: 'History', exact: true }).click()
  await expect.poll(() => api.refreshes.length).toBeGreaterThan(0)
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem('access_token'))).not.toBe(originalToken)
  // Fast-forward skips interval ticks. Let a renewal already in flight for
  // older input finish, then execute the next normal session-check interval.
  await page.clock.fastForward(30000)
  await expect.poll(() => page.evaluate(() => Number(sessionStorage.getItem('mangopoint.session.expiresAt')) - Date.now()))
    .toBeGreaterThan(14 * 60000)
  await page.clock.fastForward(30000)
  await expect(page.getByRole('button', { name: 'History', exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('button', { name: 'History', exact: true })).toBeVisible()
  await page.clock.fastForward(14 * 60000 + 100)
  await expect(page.locator('#login-identifier')).toBeVisible()
  await expect(page.getByRole('status').filter({ hasText: '15 minutes of inactivity' })).toBeVisible()
})

test('successful password change signs out the current and second device; a wrong password does not', async ({ page, browser }) => {
  const api = server(), secondContext = await browser.newContext()
  const second = await secondContext.newPage()
  try {
    await api.connect(page)
    await api.connect(second)
    await signIn(page)
    await signIn(second)
    await page.getByRole('button', { name: 'Open settings', exact: true }).click()
    await page.locator('#settings-current-password').fill('incorrect')
    await page.locator('#settings-new-password').fill('new-password-123')
    await page.locator('#settings-confirm-password').fill('new-password-123')
    await page.getByRole('button', { name: 'Change password', exact: true }).click()
    await expect(page.getByText('Current password is incorrect.', { exact: true })).toBeVisible()
    await expect(second.getByRole('button', { name: 'History', exact: true })).toBeVisible()
    await page.locator('#settings-current-password').fill('old-password')
    await page.getByRole('button', { name: 'Change password', exact: true }).click()
    await expect(page.locator('#login-identifier')).toBeVisible()
    await expect(page.getByRole('status').filter({ hasText: 'signed out on all devices' })).toBeVisible()
    await second.clock.fastForward(30100)
    await expect(second.locator('#login-identifier')).toBeVisible()
    await signIn(page, 'new-password-123')
  } finally { await secondContext.close() }
})

test('an in-flight renewal cannot restore a session after logout', async ({ page }) => {
  const api = server()
  await api.connect(page)
  await signIn(page)
  let release
  api.holdRefresh(async (route, response) => {
    await new Promise((resolve) => { release = resolve })
    await route.fulfill({ json: response })
  })
  await page.clock.fastForward(14 * 60000)
  await page.getByRole('button', { name: 'History', exact: true }).click()
  await expect.poll(() => Boolean(release)).toBe(true)
  await page.getByRole('button', { name: /Logout/ }).click()
  await page.getByRole('alertdialog').getByRole('button', { name: 'Log out', exact: true }).click()
  await expect(page.locator('#login-identifier')).toBeVisible()
  const finished = page.waitForResponse((response) => response.url().endsWith('/auth/session/refresh'))
  release()
  await finished
  await expect(page.locator('#login-identifier')).toBeVisible()
  expect(await page.evaluate(() => sessionStorage.getItem('access_token'))).toBeNull()
})

for (const width of [1440, 390]) {
  test(`logout requires confirmation and cancellation preserves the session at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 844 })
    const api = server()
    await api.connect(page)
    let logoutRequests = 0
    page.on('request', (request) => {
      if (new URL(request.url()).pathname === '/auth/logout') logoutRequests++
    })
    await signIn(page)
    if (width < 768) await page.getByRole('button', { name: 'Open simulation workspace', exact: true }).click()
    await page.locator('#sidebar-tab-simulate').click()
    await page.locator('#days-flowering').fill('75')
    const token = await page.evaluate(() => sessionStorage.getItem('access_token'))
    const logout = page.getByRole('button', { name: 'Logout', exact: true })
    const dialog = page.getByRole('alertdialog', { name: 'Log out of MangoPoint?', exact: true })

    for (const dismiss of ['cancel', 'escape', 'close', 'backdrop']) {
      await logout.click()
      await expect(dialog).toBeVisible()
      await expect(dialog.getByRole('button', { name: 'Cancel', exact: true })).toBeFocused()
      expect(logoutRequests).toBe(0)
      if (dismiss === 'cancel') {
        // Focus stays within the dialog, and Enter on the initial button is safe.
        await page.keyboard.press('Shift+Tab')
        await expect(dialog.getByRole('button', { name: 'Close logout confirmation', exact: true })).toBeFocused()
        await page.keyboard.press('Shift+Tab')
        await expect(dialog.getByRole('button', { name: 'Log out', exact: true })).toBeFocused()
        await page.keyboard.press('Tab')
        await expect(dialog.getByRole('button', { name: 'Close logout confirmation', exact: true })).toBeFocused()
        await page.keyboard.press('Tab')
        await page.keyboard.press('Enter')
      } else if (dismiss === 'escape') await page.keyboard.press('Escape')
      else if (dismiss === 'close') await dialog.getByRole('button', { name: 'Close logout confirmation', exact: true }).click()
      else await page.locator('.logout-confirmation-backdrop').click({ position: { x: 4, y: 4 } })
      await expect(dialog).toHaveCount(0)
      await expect(logout).toBeFocused()
      await expect(page.locator('#days-flowering')).toHaveValue('75')
      expect(await page.evaluate(() => sessionStorage.getItem('access_token'))).toBe(token)
      expect(logoutRequests).toBe(0)
    }

    await logout.click()
    const box = await dialog.boundingBox()
    expect(box.x).toBeGreaterThanOrEqual(0)
    expect(box.x + box.width).toBeLessThanOrEqual(width)
    await page.screenshot({ path: testInfo.outputPath('logout-confirmation.png') })
    await dialog.getByRole('button', { name: 'Log out', exact: true }).click()
    await expect(page.locator('#login-identifier')).toBeVisible()
    expect(await page.evaluate(() => sessionStorage.getItem('access_token'))).toBeNull()
    await expect.poll(() => logoutRequests).toBe(1)
  })
}
