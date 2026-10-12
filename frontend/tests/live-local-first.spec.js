import { expect, test } from '@playwright/test'

test('the deployed PWA reaches the local companion and retains its app shell offline', async ({ context, page }) => {
  await page.goto('/login')
  const localStatus = page.getByText('Local-first mode: simulations and records use this device.')
  await expect(localStatus).toBeVisible()

  await page.getByRole('button', { name: 'Close connection status' }).click()
  await expect(localStatus).toBeHidden()
  await page.reload({ waitUntil: 'domcontentloaded' })
  await expect(localStatus).toBeHidden()

  const health = await page.evaluate(async () => {
    const response = await fetch('http://127.0.0.1:8000/health', {
      cache: 'no-store',
      targetAddressSpace: 'loopback',
    })
    return { ok: response.ok, body: await response.json() }
  })
  expect(health.ok).toBe(true)
  expect(health.body.status).toBe('healthy')
  expect(health.body.database).toBe('connected')

  await page.waitForFunction(async () => {
    await navigator.serviceWorker.ready
    return Boolean(navigator.serviceWorker.controller)
  })
  await context.setOffline(true)
  await page.reload({ waitUntil: 'domcontentloaded' })

  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible()
})
