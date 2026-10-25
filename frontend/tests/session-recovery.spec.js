import { expect, test } from '@playwright/test'

// All accounts, codes and API responses are isolated fixtures. No real email
// is sent and no production session or farm record is changed.
async function recoveryServer(page) {
  await page.clock.install()
  const state = { local: true, delivery: true, oldSessions: 2, requests: [], sequence: 0,
    challenge: null, hold: null, unavailable: false, slotsFilledLate: false }
  const user = { user_id: 9, username: 'recovery-test', full_name: 'Recovery Test', role: 'operator' }
  await page.route(/arcgisonline|tile.openstreetmap|demotiles.maplibre/, (route) => route.abort())
  await page.route(/\/(health|auth|orchards|weather|monitoring|simulation|observations|alerts|sync|evaluation|validation)(\/|\?|$)/, async (route) => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname
    const body = request.method() === 'POST' ? request.postDataJSON() : null
    state.requests.push({ path, host: url.host, body, method: request.method() })
    if (path === '/health') return state.local
      ? route.fulfill({ json: { status: 'healthy', database: 'connected' } }) : route.abort()
    if (state.unavailable) return route.abort()
    const issue = () => ({ verification_required: true, session_recovery: true,
      challenge_id: `00000000-0000-0000-0000-${String(++state.sequence).padStart(12, '0')}`,
      masked_email: 'o***@example.test', resend_after_seconds: 60,
      expires_at: new Date(Date.now() + 300000).toISOString() })
    if (path === '/auth/login') {
      if (body.password !== 'fixture-password') return route.fulfill({ status: 401, json: { detail: 'Invalid credentials.' } })
      if (!body.recover_sessions && (state.oldSessions === 2 || state.slotsFilledLate)) return route.fulfill({ status: 409,
        json: { detail: 'This account already has two active sessions. Use email-verified session recovery to sign out other sessions and sign in here.' } })
      if (!state.delivery) return route.fulfill({ status: 503, json: { detail: 'Could not send your sign-in code.' } })
      state.challenge = { ...issue(), session_recovery: body.recover_sessions }
      return route.fulfill({ json: state.challenge })
    }
    if (path === '/auth/login/resend') {
      state.challenge = { ...issue(), session_recovery: state.challenge.session_recovery }
      return route.fulfill({ json: state.challenge })
    }
    if (path === '/auth/login/verify') {
      if (!state.challenge || body.challenge_id !== state.challenge.challenge_id || body.code !== '123456') {
        return route.fulfill({ status: 400, json: { detail: 'Incorrect verification code.' } })
      }
      if (!state.challenge.session_recovery && state.slotsFilledLate) {
        state.challenge = null
        return route.fulfill({ status: 409, json: { detail: 'This account already has two active sessions.' } })
      }
      if (state.hold) await state.hold()
      state.oldSessions = 0
      state.challenge = null
      return route.fulfill({ json: { access_token: 'isolated-recovered-session', user,
        expires_at: new Date(Date.now() + 900000).toISOString() } })
    }
    if (path === '/auth/me') return route.fulfill({ json: { user } })
    if (request.method() !== 'GET') return route.fulfill({ status: 400, json: { detail: 'Unexpected fixture write.' } })
    if (path === '/orchards') return route.fulfill({ json: { orchards: [] } })
    if (path === '/simulation/runs') return route.fulfill({ json: { runs: [] } })
    if (path === '/alerts') return route.fulfill({ json: { alerts: [] } })
    return route.fulfill({ status: 503, json: { detail: 'Isolated fixture service unavailable.' } })
  })
  return state
}

async function attemptLogin(page) {
  await page.goto('/login')
  await page.getByLabel('Username or email').fill('recovery-test')
  await page.getByLabel('Password', { exact: true }).fill('fixture-password')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
}

for (const width of [1440, 390]) {
  test(`full-session recovery requires explicit code confirmation and preserves its API at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 })
    const state = await recoveryServer(page)
    await attemptLogin(page)
    const recoveryDialog = page.getByRole('alertdialog', { name: 'Two sessions are active', exact: true })
    await expect(recoveryDialog).toBeVisible()
    await expect(recoveryDialog.getByRole('button', { name: 'Cancel', exact: true })).toBeFocused()
    expect(state.requests.filter((request) => request.body?.recover_sessions)).toHaveLength(0)
    const modalBox = await recoveryDialog.boundingBox()
    expect(modalBox.x).toBeGreaterThanOrEqual(0)
    expect(modalBox.x + modalBox.width).toBeLessThanOrEqual(width)
    await page.screenshot({ path: testInfo.outputPath('session-recovery-modal.png') })
    expect(state.oldSessions).toBe(2)
    // Companion availability changes after the full-session response. Recovery
    // must return to the same database that owns those sessions.
    state.local = false
    await page.evaluate(() => window.dispatchEvent(new Event('online')))
    await page.getByRole('button', { name: 'Email a recovery code', exact: true }).click()
    await expect(page.getByRole('status').filter({ hasText: 'Unsaved work' })).toBeVisible()
    const confirm = page.getByRole('button', { name: 'Sign out other sessions and sign in', exact: true })
    await expect(confirm).toBeDisabled()
    const input = page.getByRole('textbox', { name: 'Digit 1 of 6', exact: true })
    await input.fill('000000')
    // Completing a recovery code must not submit automatically.
    expect(state.requests.filter((request) => request.path === '/auth/login/verify')).toHaveLength(0)
    await confirm.click()
    await expect(page.getByRole('alert')).toContainText('Incorrect verification code')
    expect(state.oldSessions).toBe(2)
    expect(await page.evaluate(() => sessionStorage.getItem('access_token'))).toBeNull()
    await input.fill('123456')
    expect(state.oldSessions).toBe(2)
    const box = await confirm.boundingBox()
    expect(box.x).toBeGreaterThanOrEqual(0)
    expect(box.x + box.width).toBeLessThanOrEqual(width)
    await page.screenshot({ path: testInfo.outputPath('session-recovery-confirmation.png') })
    await confirm.focus()
    await page.keyboard.press('Enter')
    await expect(page.getByRole('button', { name: 'Logout', exact: true })).toBeVisible()
    expect(state.oldSessions).toBe(0)
    const auth = state.requests.filter((request) => request.path.startsWith('/auth/'))
    expect(auth.every((request) => request.host === '127.0.0.1:8000')).toBe(true)
    expect(auth.filter((request) => request.path === '/auth/login').map((request) => request.body.recover_sessions)).toEqual([false, true])
    expect(state.requests.filter((request) => request.method !== 'GET' && !request.path.startsWith('/auth/'))).toEqual([])
  })
}

test('delivery failures and cancellation leave existing sessions untouched; resend retains recovery mode', async ({ page }) => {
  const state = await recoveryServer(page)
  await attemptLogin(page)
  state.delivery = false
  await page.getByRole('button', { name: 'Email a recovery code', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Could not send')
  expect(state.oldSessions).toBe(2)
  state.delivery = true
  await page.getByRole('button', { name: 'Email a recovery code', exact: true }).click()
  const first = state.challenge.challenge_id
  await page.clock.fastForward(61000)
  await page.getByRole('button', { name: 'Resend code', exact: true }).click()
  await expect.poll(() => state.challenge.challenge_id).not.toBe(first)
  await expect(page.getByRole('button', { name: 'Sign out other sessions and sign in', exact: true })).toBeVisible()
  expect(state.oldSessions).toBe(2)
  await page.getByRole('button', { name: 'Start again', exact: true }).click()
  await expect(page.getByLabel('Password', { exact: true })).toHaveValue('')
  expect(state.oldSessions).toBe(2)
  expect(await page.evaluate(() => sessionStorage.getItem('access_token'))).toBeNull()
})

test('capacity filled during ordinary verification returns to password entry with a recovery option', async ({ page }) => {
  const state = await recoveryServer(page)
  state.oldSessions = 1
  await attemptLogin(page)
  state.slotsFilledLate = true
  await page.getByRole('textbox', { name: 'Digit 1 of 6', exact: true }).fill('123456')
  const reopen = page.getByRole('button', { name: 'Recover account access', exact: true })
  await expect(reopen).toBeVisible()
  await expect(reopen).toBeEnabled()
  await expect(page.getByLabel('Password', { exact: true })).toHaveValue('')
  await reopen.click()
  await expect(page.getByLabel('Password', { exact: true })).toBeFocused()
  await expect(page.getByRole('alertdialog')).toHaveCount(0)
  await page.getByLabel('Password', { exact: true }).fill('fixture-password')
  await reopen.click()
  await page.getByRole('button', { name: 'Email a recovery code', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Sign out other sessions and sign in', exact: true })).toBeVisible()
})

test('recovery is available before a failed sign-in and still requires credentials and confirmation', async ({ page }) => {
  const state = await recoveryServer(page)
  await page.goto('/login')
  const recover = page.getByRole('button', { name: 'Recover account access', exact: true })
  await expect(recover).toBeVisible()
  await recover.click()
  await expect(page.getByLabel('Username or email')).toBeFocused()
  await expect(page.getByRole('alertdialog')).toHaveCount(0)
  await page.getByLabel('Username or email').fill('recovery-test')
  await recover.click()
  await expect(page.getByLabel('Password', { exact: true })).toBeFocused()
  await page.getByLabel('Password', { exact: true }).fill('fixture-password')
  await recover.click()
  const modal = page.getByRole('alertdialog', { name: 'Recover account access', exact: true })
  await expect(modal).toBeVisible()
  expect(state.requests.filter((request) => request.path === '/auth/login')).toHaveLength(0)
  await modal.getByRole('button', { name: 'Email a recovery code', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Sign out other sessions and sign in', exact: true })).toBeVisible()
  expect(state.requests.filter((request) => request.path === '/auth/login').map((request) => request.body.recover_sessions)).toEqual([true])
  expect(state.oldSessions).toBe(2)
})

test('a late successful recovery response cannot sign in after leaving the login screen', async ({ page }) => {
  const state = await recoveryServer(page)
  await attemptLogin(page)
  await page.getByRole('button', { name: 'Email a recovery code', exact: true }).click()
  let release
  state.hold = () => new Promise((resolve) => { release = resolve })
  await page.getByRole('textbox', { name: 'Digit 1 of 6', exact: true }).fill('123456')
  await page.getByRole('button', { name: 'Sign out other sessions and sign in', exact: true }).click()
  await expect.poll(() => Boolean(release)).toBe(true)
  await page.evaluate(() => { history.pushState({}, '', '/forgot-password'); dispatchEvent(new PopStateEvent('popstate')) })
  const finished = page.waitForResponse((response) => response.url().endsWith('/auth/login/verify'))
  release()
  await finished
  await expect(page.getByRole('heading', { name: 'Reset your password' })).toBeVisible()
  expect(await page.evaluate(() => sessionStorage.getItem('access_token'))).toBeNull()
})

for (const width of [1440, 390]) {
  test(`recovery modal dismissal preserves input and sends no recovery request at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    const state = await recoveryServer(page)
    await attemptLogin(page)
    const modal = page.getByRole('alertdialog', { name: 'Two sessions are active', exact: true })
    const reopen = page.getByRole('button', { name: 'Recover account access', exact: true })
    for (const dismiss of ['cancel', 'escape', 'close', 'backdrop']) {
      await expect(modal).toBeVisible()
      await expect(modal.getByRole('button', { name: 'Cancel', exact: true })).toBeFocused()
      expect(await page.locator('#root').evaluate((element) => element.inert)).toBe(true)
      await page.keyboard.press('Shift+Tab')
      await expect(modal.getByRole('button', { name: 'Close session recovery', exact: true })).toBeFocused()
      await page.keyboard.press('Shift+Tab')
      await expect(modal.getByRole('button', { name: 'Email a recovery code', exact: true })).toBeFocused()
      await page.keyboard.press('Tab')
      await expect(modal.getByRole('button', { name: 'Close session recovery', exact: true })).toBeFocused()
      if (dismiss === 'cancel') await modal.getByRole('button', { name: 'Cancel', exact: true }).click()
      else if (dismiss === 'escape') await page.keyboard.press('Escape')
      else if (dismiss === 'close') await modal.getByRole('button', { name: 'Close session recovery', exact: true }).click()
      else await page.locator('.session-recovery-backdrop').click({ position: { x: 4, y: 4 } })
      await expect(modal).toHaveCount(0)
      await expect(reopen).toBeFocused()
      await expect(page.getByLabel('Username or email')).toHaveValue('recovery-test')
      await expect(page.getByLabel('Password', { exact: true })).toHaveValue('fixture-password')
      expect(await page.locator('#root').evaluate((element) => element.inert)).toBe(false)
      expect(await page.evaluate(() => document.body.style.overflow)).not.toBe('hidden')
      expect(state.requests.filter((request) => request.body?.recover_sessions)).toHaveLength(0)
      expect(state.oldSessions).toBe(2)
      if (dismiss !== 'backdrop') await reopen.click()
    }
  })
}
