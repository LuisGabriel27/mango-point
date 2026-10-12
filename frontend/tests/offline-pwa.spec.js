import { expect, test } from '@playwright/test'

test('the production app shell reloads after the browser goes offline', async ({ context, page }) => {
  await page.goto('/login')
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible()
  await page.waitForFunction(async () => {
    if (!('serviceWorker' in navigator)) return false
    await navigator.serviceWorker.ready
    return Boolean(navigator.serviceWorker.controller)
  })
  const cachedUrls = await page.evaluate(async () => {
    const keys = await caches.keys()
    const requests = await Promise.all(keys.map(async (key) => (await caches.open(key)).keys()))
    return requests.flat().map((request) => request.url)
  })
  expect(cachedUrls.some((url) => /\/assets\/index-.*\.js$/.test(url))).toBe(true)
  expect(cachedUrls.some((url) => /\/assets\/index-.*\.css$/.test(url))).toBe(true)

  await context.setOffline(true)
  await page.reload({ waitUntil: 'domcontentloaded' })

  await expect(page).toHaveTitle('MangoPoint Dashboard')
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible()
  await expect(page.getByText('Offline companion unavailable')).toBeVisible()
  await page.getByRole('button', { name: 'Close connection status' }).click()
  await expect(page.getByRole('status')).toBeHidden()
  await page.reload({ waitUntil: 'domcontentloaded' })
  await expect(page.getByRole('status')).toBeHidden()
})
