import { expect, test } from '@playwright/test'

test('a verified visitor without a local companion uses the fixed production API', async ({ context, page }) => {
  test.skip(!process.env.MANGOPOINT_TEST_ACCESS_TOKEN, 'Provide an existing email-verified session token in the test process environment. This check sends no login email.')
  await page.addInitScript((token) => sessionStorage.setItem('access_token', token), process.env.MANGOPOINT_TEST_ACCESS_TOKEN)
  await context.route(/http:\/\/(127\.0\.0\.1|localhost):8000\//, (route) => route.abort())
  const remoteFailures = []
  const pageErrors = []
  page.on('requestfailed', (request) => {
    if (new URL(request.url()).pathname.startsWith('/api/')) remoteFailures.push(request.method())
  })
  page.on('pageerror', (error) => pageErrors.push(error.message))
  await page.goto('/')
  const health = await page.evaluate(async () => {
    const response = await fetch('/api/health', { cache: 'no-store' })
    return { status: response.status, body: await response.json() }
  })
  expect(health.status).toBe(200)
  expect(health.body.database).toBe('connected')
  await expect(page.getByRole('button', { name: 'Logout' })).toBeVisible({ timeout: 30_000 })
  const records = await page.evaluate(async () => {
    const response = await fetch('/api/orchards', {
      cache: 'no-store', headers: { Authorization: `Bearer ${sessionStorage.getItem('access_token')}` },
    })
    return { status: response.status, isJson: response.headers.get('content-type')?.includes('application/json') }
  })
  expect(records).toEqual({ status: 200, isJson: true })
  expect(remoteFailures).toEqual([])
  expect(pageErrors).toEqual([])
  await expect(page.getByText('Network Error', { exact: true })).toHaveCount(0)
})
