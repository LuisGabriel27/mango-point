import { expect, test } from '@playwright/test'

// Every API response and email code here is synthetic; no messages or records
// are sent to the application server.
async function emailServer(page) {
  await page.clock.install()
  const state = { local: true, delivery: true, legacy: false, verifyUnavailable: false, validCode: '123456', requests: [], sequence: 0, challenge: null, holdVerify: null }
  const user = { user_id: 7, username: 'email-test', full_name: 'Email Test', email: 'owner@example.test', role: 'operator' }
  const issue = async () => {
    state.challenge = `00000000-0000-0000-0000-${String(++state.sequence).padStart(12, '0')}`
    return { verification_required: true, challenge_id: state.challenge, masked_email: 'o***@example.test',
      expires_at: new Date(await page.evaluate(() => Date.now()) + 300000).toISOString(), resend_after_seconds: 60 }
  }
  await page.route(/\/(health|auth|orchards|weather|monitoring|simulation|observations|alerts|sync|evaluation|validation)(\/|\?|$)/, async (route) => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname
    const body = request.method() === 'POST' ? request.postDataJSON() : null
    state.requests.push({ path, host: url.host, body, method: request.method() })
    if (path === '/health') return state.local ? route.fulfill({ json: { status: 'healthy', database: 'connected' } }) : route.abort()
    if (path === '/auth/login') {
      if (!state.delivery) return route.fulfill({ status: 503, json: { detail: 'Could not send your sign-in code. Check your internet connection and try again.' } })
      if (state.legacy) return route.fulfill({ json: { access_token: 'unverified-old-api-token', user } })
      return route.fulfill({ json: await issue() })
    }
    if (path === '/auth/login/resend') return route.fulfill({ json: await issue() })
    if (path === '/auth/login/verify') {
      if (state.verifyUnavailable) return route.abort()
      if (body.challenge_id !== state.challenge || body.code !== state.validCode) {
        return route.fulfill({ status: 400, json: { detail: 'Incorrect verification code. 4 attempts remaining.' } })
      }
      const response = { access_token: 'isolated-email-verified-token', user,
        expires_at: new Date(await page.evaluate(() => Date.now()) + 900000).toISOString() }
      if (state.holdVerify) return state.holdVerify(route, response)
      return route.fulfill({ json: response })
    }
    if (path === '/auth/me') return route.fulfill({ json: { user } })
    if (request.method() !== 'GET') return route.fulfill({ status: 400, json: { detail: 'Unexpected fixture write.' } })
    if (path === '/orchards') return route.fulfill({ json: { orchards: [] } })
    if (path === '/simulation/runs') return route.fulfill({ json: { runs: [] } })
    if (path === '/alerts') return route.fulfill({ json: { alerts: [] } })
    return route.fulfill({ status: 503, json: { detail: 'Isolated test: unavailable.' } })
  })
  return state
}

async function enterPassword(page) {
  await page.goto('/login')
  await page.getByLabel('Username or email').fill('email-test')
  await page.getByLabel('Password', { exact: true }).fill('private-fixture-password')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
}

test('password and incorrect code grant no session; the verified code completes login', async ({ page }) => {
  const state = await emailServer(page)
  await enterPassword(page)
  await expect(page.getByRole('heading', { name: 'Check your email' })).toBeVisible()
  await expect(page.getByRole('textbox', { name: 'Digit 1 of 6', exact: true })).toBeFocused()
  expect(await page.evaluate(() => sessionStorage.getItem('access_token'))).toBeNull()
  await expect(page.locator('#login-password')).toHaveCount(0)
  await page.getByRole('textbox', { name: 'Digit 1 of 6', exact: true }).fill('000000')
  await expect(page.getByRole('alert')).toContainText('Incorrect verification code')
  expect(await page.evaluate(() => sessionStorage.getItem('access_token'))).toBeNull()
  await expect(page.getByRole('textbox', { name: 'Digit 1 of 6', exact: true })).toBeFocused()
  expect(await page.locator('.login-code-digit').evaluateAll((inputs) => inputs.map((input) => input.value)))
    .toEqual(['', '', '', '', '', ''])
  await page.clock.fastForward(2000)
  expect(state.requests.filter((request) => request.path === '/auth/login/verify')).toHaveLength(1)
  await page.getByRole('textbox', { name: 'Digit 1 of 6', exact: true }).fill('123456')
  await expect(page.getByRole('button', { name: 'Logout', exact: true })).toBeVisible()
  expect(await page.evaluate(() => sessionStorage.getItem('access_token'))).toBe('isolated-email-verified-token')
  expect(state.requests.filter((request) => request.method !== 'GET').map((request) => request.path))
    .toEqual(['/auth/login', '/auth/login/verify', '/auth/login/verify'])
})

test('resend waits for cooldown, replaces the challenge and clears the code', async ({ page }) => {
  const state = await emailServer(page)
  await enterPassword(page)
  await expect(page.getByRole('button', { name: /Resend code in/ })).toBeDisabled()
  await page.getByRole('textbox', { name: 'Digit 1 of 6', exact: true }).fill('654321')
  await expect(page.getByRole('alert')).toContainText('Incorrect verification code')
  const first = state.challenge
  await page.clock.fastForward(61000)
  await page.getByRole('button', { name: 'Resend code', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: 'A new code was sent' })).toBeVisible()
  expect(state.challenge).not.toBe(first)
  await expect(page.getByRole('textbox', { name: 'Digit 1 of 6', exact: true })).toHaveValue('')
  await expect(page.getByRole('textbox', { name: 'Digit 1 of 6', exact: true })).toBeFocused()
  expect(await page.evaluate(() => sessionStorage.getItem('access_token'))).toBeNull()
})

test('expired challenges explain the sign-in refresh and restore no partial session', async ({ page }) => {
  await emailServer(page)
  await enterPassword(page)
  await expect(page.getByRole('textbox', { name: 'Digit 1 of 6', exact: true })).toBeVisible()
  await page.clock.fastForward(300100)
  await expect(page.getByRole('status').filter({ hasText: 'This code has expired' })).toBeVisible()
  for (const input of await page.locator('.login-code-digit').all()) await expect(input).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Verify and sign in' })).toHaveCount(0)
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible()
  expect(await page.evaluate(() => sessionStorage.getItem('access_token'))).toBeNull()
})

test('mail failure and an old password-only API both leave the user signed out', async ({ page }) => {
  const state = await emailServer(page)
  state.delivery = false
  await enterPassword(page)
  await expect(page.getByRole('alert')).toContainText('Could not send your sign-in code')
  state.delivery = true
  state.legacy = true
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('server needs the email sign-in update')
  expect(await page.evaluate(() => sessionStorage.getItem('access_token'))).toBeNull()
})

test('code verification stays on its issuing API when companion availability changes', async ({ page }) => {
  const state = await emailServer(page)
  await enterPassword(page)
  await expect(page.getByRole('textbox', { name: 'Digit 1 of 6', exact: true })).toBeVisible()
  state.local = false
  await page.evaluate(() => window.dispatchEvent(new Event('online')))
  await page.getByRole('textbox', { name: 'Digit 1 of 6', exact: true }).fill('123456')
  await expect(page.getByRole('button', { name: 'Logout', exact: true })).toBeVisible()
  const auth = state.requests.filter((request) => ['/auth/login', '/auth/login/verify'].includes(request.path))
  expect(auth.map((request) => request.host)).toEqual(['127.0.0.1:8000', '127.0.0.1:8000'])
})

test('a verification response cannot sign in after leaving the login screen', async ({ page }) => {
  const state = await emailServer(page)
  let release
  state.holdVerify = async (route, response) => {
    await new Promise((resolve) => { release = resolve })
    await route.fulfill({ json: response })
  }
  await enterPassword(page)
  await page.getByRole('textbox', { name: 'Digit 1 of 6', exact: true }).fill('123456')
  await expect.poll(() => Boolean(release)).toBe(true)
  await page.evaluate(() => { history.pushState({}, '', '/forgot-password'); dispatchEvent(new PopStateEvent('popstate')) })
  await expect(page.getByRole('heading', { name: 'Reset your password' })).toBeVisible()
  const finished = page.waitForResponse((response) => response.url().endsWith('/auth/login/verify'))
  release()
  await finished
  await expect(page.getByRole('heading', { name: 'Reset your password' })).toBeVisible()
  expect(await page.evaluate(() => sessionStorage.getItem('access_token'))).toBeNull()
})

test('an unreachable issuing API leaves the user signed out without retrying another server', async ({ page }) => {
  const state = await emailServer(page)
  await enterPassword(page)
  await expect(page.getByRole('textbox', { name: 'Digit 1 of 6', exact: true })).toBeVisible()
  state.local = false
  state.verifyUnavailable = true
  await page.evaluate(() => window.dispatchEvent(new Event('online')))
  await page.getByRole('textbox', { name: 'Digit 1 of 6', exact: true }).fill('123456')
  await expect(page.getByRole('alert')).toContainText('Cannot reach MangoPoint on this device')
  expect(await page.evaluate(() => sessionStorage.getItem('access_token'))).toBeNull()
  expect(state.requests.filter((request) => request.path === '/auth/login/verify').map((request) => request.host))
    .toEqual(['127.0.0.1:8000'])
  await page.clock.fastForward(2000)
  expect(state.requests.filter((request) => request.path === '/auth/login/verify')).toHaveLength(1)
  state.verifyUnavailable = false
  await page.getByRole('button', { name: 'Verify and sign in', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Logout', exact: true })).toBeVisible()
  expect(state.requests.filter((request) => request.path === '/auth/login/verify')).toHaveLength(2)
})

test('only digits are kept and completing the code sends one request even with repeated submissions', async ({ page }) => {
  const state = await emailServer(page)
  let release
  state.holdVerify = async (route, response) => {
    await new Promise((resolve) => { release = resolve })
    await route.fulfill({ json: response })
  }
  await enterPassword(page)
  const input = page.getByRole('textbox', { name: 'Digit 1 of 6', exact: true })
  const boxes = page.getByRole('group', { name: 'Email verification code', exact: true }).getByRole('textbox')
  await expect(boxes).toHaveCount(6)
  await expect(input).toHaveAttribute('inputmode', 'numeric')
  await input.fill('ab12')
  expect(await boxes.evaluateAll((inputs) => inputs.map((field) => field.value))).toEqual(['1', '2', '', '', '', ''])
  await input.fill('12345')
  await expect(boxes.nth(5)).toBeFocused()
  await page.keyboard.type('x-')
  expect(await boxes.evaluateAll((inputs) => inputs.map((field) => field.value))).toEqual(['1', '2', '3', '4', '5', ''])
  expect(state.requests.filter((request) => request.path === '/auth/login/verify')).toHaveLength(0)
  await page.keyboard.type('6')
  await expect.poll(() => Boolean(release)).toBe(true)
  try {
    await expect(input).toBeDisabled()
    await page.locator('.login-form').evaluate((form) => { form.requestSubmit(); form.requestSubmit() })
    await page.clock.fastForward(2000)
    expect(state.requests.filter((request) => request.path === '/auth/login/verify')).toHaveLength(1)
  } finally { release() }
  await expect(page.getByRole('button', { name: 'Logout', exact: true })).toBeVisible()
})

test('pasted codes retain leading zeros and discard formatting and extra characters', async ({ page }) => {
  const state = await emailServer(page)
  state.validCode = '001234'
  await enterPassword(page)
  await page.getByRole('textbox', { name: 'Digit 3 of 6', exact: true }).evaluate((input) => {
    const clipboardData = new DataTransfer()
    clipboardData.setData('text/plain', 'Code: 001 234 567')
    input.dispatchEvent(new ClipboardEvent('paste', { clipboardData, bubbles: true, cancelable: true }))
  })
  await expect(page.getByRole('button', { name: 'Logout', exact: true })).toBeVisible()
  const requests = state.requests.filter((request) => request.path === '/auth/login/verify')
  expect(requests).toHaveLength(1)
  expect(requests[0].body.code).toBe('001234')
})

test('autofilled values are capped at six digits before automatic verification', async ({ page }) => {
  const state = await emailServer(page)
  await enterPassword(page)
  await page.getByRole('textbox', { name: 'Digit 1 of 6', exact: true }).evaluate((input) => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, '123456789')
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await expect(page.getByRole('button', { name: 'Logout', exact: true })).toBeVisible()
  const requests = state.requests.filter((request) => request.path === '/auth/login/verify')
  expect(requests).toHaveLength(1)
  expect(requests[0].body.code).toBe('123456')
})

test('Backspace, Delete and arrow keys edit individual positions without shifting other digits', async ({ page }) => {
  const state = await emailServer(page)
  await enterPassword(page)
  const boxes = page.locator('.login-code-digit')
  await expect(boxes.first()).toBeFocused()
  await page.keyboard.type('1234')
  await expect(boxes.nth(4)).toBeFocused()
  await page.keyboard.press('ArrowLeft')
  await page.keyboard.type('x')
  await page.keyboard.type('9')
  expect(await boxes.evaluateAll((inputs) => inputs.map((input) => input.value))).toEqual(['1', '2', '3', '9', '', ''])
  await page.keyboard.press('Backspace')
  await expect(boxes.nth(3)).toBeFocused()
  await page.keyboard.press('ArrowLeft')
  await page.keyboard.press('Delete')
  expect(await boxes.evaluateAll((inputs) => inputs.map((input) => input.value))).toEqual(['1', '2', '', '', '', ''])
  await page.keyboard.press('Home')
  await expect(boxes.first()).toBeFocused()
  await page.keyboard.press('Backspace')
  await expect(boxes.first()).toBeFocused()
  await page.keyboard.press('End')
  await expect(boxes.last()).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('button', { name: 'Start again', exact: true })).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('button', { name: 'Terms and Conditions', exact: true })).toBeFocused()
  expect(state.requests.filter((request) => request.path === '/auth/login/verify')).toHaveLength(0)
})

for (const width of [1440, 390, 320]) {
  test(`six individual code boxes advance focus and sign in automatically at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 844 })
    const state = await emailServer(page)
    await enterPassword(page)
    const boxes = page.getByRole('group', { name: 'Email verification code', exact: true }).getByRole('textbox')
    await expect(boxes).toHaveCount(6)
    await expect(boxes.first()).toBeFocused()
    await page.screenshot({ path: testInfo.outputPath('six-code-boxes-empty.png') })
    await page.keyboard.type('12345')
    await expect(boxes.last()).toBeFocused()
    expect(await boxes.evaluateAll((inputs) => inputs.map((input) => input.value))).toEqual(['1', '2', '3', '4', '5', ''])
    await expect(page.getByRole('button', { name: 'Verify and sign in' })).toHaveCount(0)
    const sizes = await boxes.evaluateAll((inputs) => inputs.map((input) => {
      const { width, height } = input.getBoundingClientRect()
      return { width, height }
    }))
    for (const size of sizes) {
      expect(size.width).toBeLessThanOrEqual(45)
      expect(Math.abs(size.width - size.height)).toBeLessThan(1)
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.screenshot({ path: testInfo.outputPath('six-code-boxes-partial.png') })
    await page.keyboard.type('6')
    await expect(page.getByRole('button', { name: 'Logout', exact: true })).toBeVisible()
    const requests = state.requests.filter((request) => request.path === '/auth/login/verify')
    expect(requests).toHaveLength(1)
    expect(requests[0].body.code).toBe('123456')
  })
}
