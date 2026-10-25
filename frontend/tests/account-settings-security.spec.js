import { expect, test } from '@playwright/test'

test('blocked third login shows the session-limit explanation without creating a session', async ({ page }) => {
  await page.route('**/auth/login', (route) => route.fulfill({ status: 409, json: {
    detail: 'This account already has two active sessions. Log out on another browser or wait for an inactive session to expire, then try again.',
  } }))
  await page.goto('/login')
  await page.getByLabel('Username or email').fill('security-review')
  await page.getByLabel('Password', { exact: true }).fill('private-password')
  await page.getByRole('button', { name: /Sign in/i }).click()
  await expect(page.getByRole('alertdialog', { name: 'Two sessions are active', exact: true })).toBeVisible()
  await expect(page).toHaveURL(/\/login$/)
  expect(await page.evaluate(() => sessionStorage.getItem('access_token'))).toBeNull()
})

// All writes and email delivery are isolated browser fixtures.
async function openSettings(page) {
  const state = { requests: [], failDelete: false, recipients: [
    { recipient_id: 1, name: 'Jim', email: 'jim@example.test', is_active: true },
  ] }
  const user = { user_id: 42, username: 'security-review', full_name: 'Security Review', email: 'owner@example.test', role: 'admin' }
  await page.addInitScript(() => sessionStorage.setItem('access_token', 'isolated-settings-review'))
  await page.route(/\/(auth|orchards|weather|monitoring|simulation|observations|alerts|sync|evaluation|validation)(\/|\?|$)/, async (route) => {
    const request = route.request(), path = new URL(request.url()).pathname
    state.requests.push({ path, method: request.method(), body: request.postDataJSON() })
    if (path === '/auth/me') return route.fulfill({ json: { user } })
    if (path === '/auth/me/email/code') return route.fulfill({ json: { challenge_id: '00000000-0000-0000-0000-000000000002' } })
    if (path === '/auth/me/email') {
      if (request.postDataJSON().code !== '123456') return route.fulfill({ status: 400, json: { detail: 'Incorrect verification code.' } })
      user.email = request.postDataJSON().email
      return route.fulfill({ json: { user } })
    }
    if (path === '/orchards') return route.fulfill({ json: { orchards: [] } })
    if (path === '/weather/live') return route.fulfill({ json: { current: { temperature_c: 27, wind_speed_ms: 1, source: 'synthetic' } } })
    if (path === '/simulation/runs') return route.fulfill({ json: { runs: [] } })
    if (path === '/alerts') return route.fulfill({ json: { alerts: [] } })
    if (path === '/alerts/email/recipients') {
      if (request.method() === 'POST') {
        const recipient = { ...request.postDataJSON(), recipient_id: 2, is_active: true }
        state.recipients.push(recipient)
        return route.fulfill({ json: recipient })
      }
      return route.fulfill({ json: state.recipients })
    }
    if (path === '/alerts/email/recipients/1' && request.method() === 'DELETE') {
      if (state.failDelete) return route.fulfill({ status: 503, json: { detail: 'Could not delete this recipient. Try again.' } })
      state.recipients = state.recipients.filter((recipient) => recipient.recipient_id !== 1)
      return route.fulfill({ json: { recipient_id: 1 } })
    }
    return route.fulfill({ status: 503, json: { detail: 'Isolated test: unavailable.' } })
  })
  await page.goto('/')
  await page.getByRole('button', { name: 'Maybe later', exact: true }).click()
  await page.getByRole('button', { name: 'Open settings', exact: true }).click()
  return state
}

for (const width of [1440, 390]) {
  test(`recipient validation and nested deletion confirmation at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 844 })
    const state = await openSettings(page)
    const settings = page.getByRole('dialog', { name: 'Settings', exact: true })
    await settings.getByRole('button', { name: 'Notification emails', exact: false }).click()
    const add = settings.getByRole('button', { name: /Add recipient$/ })
    for (const email of ['not-an-email', 'person..name@example.com', 'person@-example.com', 'person@example..com']) {
      await page.locator('#settings-recipient-email').fill(email)
      await add.click()
      await expect(settings.getByText('Enter a valid email address.', { exact: true })).toBeVisible()
    }
    await page.locator('#settings-recipient-email').fill('JIM@example.test')
    await add.click()
    await expect(settings.getByText('That email address is already assigned to another recipient.', { exact: true })).toBeVisible()
    expect(state.requests.filter((request) => request.method === 'POST')).toEqual([])
    await page.locator('#settings-recipient-name').fill('<script>')
    await page.locator('#settings-recipient-email').fill('farmer+alerts@example.com')
    await add.click()
    await expect(settings.getByText('Name cannot contain control characters or angle brackets.', { exact: true })).toBeVisible()
    await page.locator('#settings-recipient-name').fill('Mango Farmer')
    await add.click()
    await expect(settings.getByText('farmer+alerts@example.com', { exact: true })).toBeVisible()

    const remove = settings.getByRole('button', { name: 'Permanently delete Jim', exact: true })
    const confirmation = page.getByRole('alertdialog', { name: 'Delete notification recipient?', exact: true })
    await remove.click()
    await expect(confirmation.getByRole('button', { name: 'Cancel', exact: true })).toBeFocused()
    await confirmation.getByRole('button', { name: 'Cancel', exact: true }).click()
    await expect(remove).toBeFocused()
    await expect(settings).toBeVisible()
    await remove.click()
    await page.keyboard.press('Escape')
    await expect(confirmation).toHaveCount(0)
    await expect(settings).toBeVisible()
    await remove.click()
    await page.locator('.confirmation-modal-backdrop').click({ position: { x: 4, y: 4 } })
    await expect(confirmation).toHaveCount(0)
    await expect(remove).toBeFocused()
    expect(state.requests.filter((request) => request.method === 'DELETE')).toEqual([])
    await remove.click()
    const box = await confirmation.boundingBox()
    expect(box.x).toBeGreaterThanOrEqual(0)
    expect(box.x + box.width).toBeLessThanOrEqual(width)
    await page.screenshot({ path: testInfo.outputPath('recipient-confirmation.png') })
    state.failDelete = true
    await confirmation.getByRole('button', { name: 'Delete recipient', exact: true }).click()
    await expect(confirmation.getByRole('alert')).toContainText('Could not delete this recipient')
    await expect(confirmation).toBeVisible()
    state.failDelete = false
    await confirmation.getByRole('button', { name: 'Delete recipient', exact: true }).click()
    await expect(confirmation).toHaveCount(0)
    await expect(settings).toBeVisible()
    await expect(remove).toHaveCount(0)
  })
}

test('recovery email requires confirmation from the existing inbox and password fields toggle independently', async ({ page }) => {
  const state = await openSettings(page)
  for (const [id, label] of [
    ['settings-email-password', 'recovery email current password'], ['settings-current-password', 'current password'],
    ['settings-new-password', 'new password'], ['settings-confirm-password', 'confirm new password'],
  ]) {
    await page.locator(`#${id}`).fill('retained-value')
    await page.getByRole('button', { name: `Show ${label}`, exact: true }).click()
    await expect(page.locator(`#${id}`)).toHaveAttribute('type', 'text')
    await expect(page.locator(`#${id}`)).toHaveValue('retained-value')
    await page.getByRole('button', { name: `Hide ${label}`, exact: true }).click()
    await expect(page.locator(`#${id}`)).toHaveAttribute('type', 'password')
  }
  const panel = page.locator('section[aria-labelledby="email-settings-title"]')
  await page.locator('#settings-recovery-email').fill('replacement@example.test')
  await panel.getByRole('button', { name: 'Send verification code', exact: true }).click()
  await expect(panel.getByRole('status')).toContainText('owner@example.test')
  expect(state.requests.filter((request) => request.method === 'PATCH')).toEqual([])
  await page.locator('#settings-email-code').fill('000000')
  await panel.getByRole('button', { name: 'Confirm recovery email', exact: true }).click()
  await expect(panel.getByText('Incorrect verification code.', { exact: true })).toBeVisible()
  await page.locator('#settings-email-code').fill('123456')
  await panel.getByRole('button', { name: 'Confirm recovery email', exact: true }).click()
  await expect(panel.getByText('Your login and recovery email was updated.', { exact: true })).toBeVisible()
})
