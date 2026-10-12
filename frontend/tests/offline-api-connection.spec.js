import { expect, test } from '@playwright/test'

test('the cached Vercel app signs in and reaches local API POST validation with browser internet blocked', async ({ context, page }) => {
  test.skip(!process.env.MANGOPOINT_TEST_USERNAME || !process.env.MANGOPOINT_TEST_PASSWORD, 'Provide an existing local account in process environment variables.')
  await page.goto('/login')
  await expect(page.getByText('Local-first mode: simulations and records use this device.')).toBeVisible()
  await page.waitForFunction(async () => {
    await navigator.serviceWorker.ready
    return Boolean(navigator.serviceWorker.controller)
  })

  // DevTools/Playwright's blanket offline mode also blocks localhost. Block
  // internet requests explicitly so the local Docker/native API stays reachable.
  await context.route(/^https?:\/\//, async (route) => {
    const url = new URL(route.request().url())
    if (url.protocol === 'http:' && url.hostname === '127.0.0.1' && url.port === '8000') {
      return route.continue()
    }
    return route.abort('internetdisconnected')
  })
  await page.reload({ waitUntil: 'domcontentloaded' })
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible()
  const remoteReachable = await page.evaluate(async () => {
    try {
      await fetch(`/api/health?offline_transport_check=${Date.now()}`, { cache: 'no-store' })
      return true
    } catch { return false }
  })
  expect(remoteReachable).toBe(false)
  const loginResponse = page.waitForResponse((response) => response.url() === 'http://127.0.0.1:8000/auth/login' && response.request().method() === 'POST')
  await page.getByLabel('Username or email').fill(process.env.MANGOPOINT_TEST_USERNAME)
  await page.getByLabel('Password', { exact: true }).fill(process.env.MANGOPOINT_TEST_PASSWORD)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  expect((await loginResponse).status()).toBe(200)
  await expect(page.getByRole('button', { name: 'Logout' })).toBeVisible()

  const localResults = await page.evaluate(async () => {
    const token = sessionStorage.getItem('access_token')
    const options = { cache: 'no-store', targetAddressSpace: 'loopback', headers: { Authorization: `Bearer ${token}` } }
    const orchards = await fetch('http://127.0.0.1:8000/orchards', options)
    const validation = await fetch('http://127.0.0.1:8000/simulation/run-simulation', {
      ...options, method: 'POST', headers: { ...options.headers, 'Content-Type': 'application/json' }, body: '{}',
    })
    return {
      orchardStatus: orchards.status,
      validationStatus: validation.status,
      validationIsJson: validation.headers.get('content-type')?.includes('application/json'),
    }
  })
  // Empty inputs fail request validation before model execution/persistence or
  // alert notification. This verifies network/auth/CORS, not a forecast result.
  expect(localResults).toEqual({ orchardStatus: 200, validationStatus: 422, validationIsJson: true })
})
