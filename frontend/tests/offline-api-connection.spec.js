import { expect, test } from '@playwright/test'

test('the cached Vercel app uses an existing verified local session with browser internet blocked', async ({ context, page }) => {
  test.skip(!process.env.MANGOPOINT_TEST_ACCESS_TOKEN, 'Provide an existing email-verified local session token in process environment variables. Fresh sign-in requires email delivery.')
  await page.addInitScript((token) => {
    if (!sessionStorage.getItem('access_token')) sessionStorage.setItem('access_token', token)
  }, process.env.MANGOPOINT_TEST_ACCESS_TOKEN)
  await page.goto('/')
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
  await expect(page.getByRole('button', { name: 'Logout', exact: true })).toBeVisible()
  const remoteReachable = await page.evaluate(async () => {
    try {
      await fetch(`/api/health?offline_transport_check=${Date.now()}`, { cache: 'no-store' })
      return true
    } catch { return false }
  })
  expect(remoteReachable).toBe(false)
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
