/* Browser checks use isolated HTTP fixtures; nothing is submitted to production. */
const assert = require('node:assert/strict')
const { mkdirSync } = require('node:fs')
const path = require('node:path')
const { chromium } = require('../frontend/node_modules/playwright')

const origin = 'http://127.0.0.1:8088'
const api = 'https://mango-point-projects.vercel.app/api'
const output = path.resolve(__dirname, '../outputs/access-website')
const admin = { user_id: 1, role: 'admin', username: 'test-admin', full_name: 'Test Administrator' }
const record = {
  request_id: 'd32f1120-a9a4-4c8c-9baf-53b7e21092f7', reference: 'MP-D32F1120A9A4',
  organization: 'Example Grower Cooperative', sector: 'cooperative', contact_name: 'Test Contact',
  email: 'contact@example.test', phone: '', location: 'Guimaras', orchard_count: 3,
  interest: 'demonstration', message: '<img src=x onerror="window.inquiryXss=true"> Request a demonstration.',
  status: 'new', notes: '', version: 1, consent_version: 'access-inquiry-v1',
  created_at: '2026-10-12T01:00:00Z', updated_at: '2026-10-12T01:00:00Z', reviewed_by_user_id: null,
}

async function main() {
  mkdirSync(output, { recursive: true })
  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  try {
    let submissions = []
    await page.route(`${api}/**`, async route => {
      assert.equal(route.request().url(), `${api}/access-requests`)
      submissions.push(route.request().postDataJSON())
      if (submissions.length === 1) return route.fulfill({ status: 503, json: { detail: 'Test service unavailable.' } })
      return route.fulfill({ status: 201, json: { reference: record.reference, created_at: record.created_at, message: 'Request received.' } })
    })
    await page.goto(origin)
    await page.keyboard.press('Tab')
    assert.equal(await page.locator(':focus').textContent(), 'Skip to content')
    await page.getByRole('button', { name: 'Send request' }).click()
    assert.equal(submissions.length, 0, 'required fields prevent a network request')
    await page.getByLabel('Organization name').fill('Example Grower Cooperative')
    await page.getByLabel('Sector', { exact: false }).selectOption('cooperative')
    await page.getByLabel('Location', { exact: false }).fill('Guimaras')
    await page.getByLabel('Contact person').fill('Test Contact')
    await page.getByLabel('Email address').fill('contact@example.test')
    await page.getByLabel('What would you like to discuss?').selectOption('demonstration')
    await page.getByLabel('Tell us about your needs').fill('We would like to discuss an orchard demonstration.')
    await page.getByRole('checkbox').check()
    await page.getByRole('button', { name: 'Send request' }).click()
    await page.getByRole('alert').waitFor({ state: 'visible' })
    assert.equal(await page.getByLabel('Organization name').inputValue(), 'Example Grower Cooperative')
    assert.equal(await page.locator('#inquiry-success').isVisible(), false)
    await page.getByRole('button', { name: 'Send request' }).click()
    await page.locator('#success-title').waitFor({ state: 'visible' })
    assert.equal(submissions[0].submission_id, submissions[1].submission_id)
    assert.equal(await page.locator(':focus').getAttribute('id'), 'success-title')
    assert.equal(await page.locator('#receipt-reference').textContent(), record.reference)
    await page.getByRole('button', { name: 'Send another request' }).click()
    assert.equal(await page.getByLabel('Organization name').inputValue(), '')
    await page.setViewportSize({ width: 360, height: 800 })
    await page.goto(origin)
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false)
    await page.screenshot({ path: path.join(output, 'mobile.png'), fullPage: true })
    await page.setViewportSize({ width: 1440, height: 1000 })
    await page.goto(origin)
    await page.screenshot({ path: path.join(output, 'desktop.png'), fullPage: true })
    console.log('PASS: public validation, failure preservation, retry identity, success focus and mobile layout.')

    await page.unroute(`${api}/**`)
    let current = { ...record }
    let rows = []
    let authRole = 'operator'
    let patchCalls = []
    let blockNextList = false
    let releaseList
    let listStarted
    const calls = []
    await page.route(`${api}/**`, async route => {
      const req = route.request()
      const url = new URL(req.url())
      const pathname = url.pathname.replace('/api', '')
      calls.push({ path: pathname, method: req.method() })
      if (pathname === '/auth/login') return route.fulfill({ json: { access_token: 'test-only-browser-token', user: { ...admin, role: authRole } } })
      if (pathname === '/auth/me') return route.fulfill({ json: { user: admin } })
      assert.equal(req.headers().authorization, 'Bearer test-only-browser-token')
      if (pathname === '/access-requests' && req.method() === 'GET') {
        if (blockNextList) {
          blockNextList = false
          listStarted()
          await new Promise(resolve => { releaseList = resolve })
        }
        const filtered = rows.filter(row => !url.searchParams.get('status') || row.status === url.searchParams.get('status'))
        return route.fulfill({ json: { requests: filtered, total: filtered.length, counts: { new: current.status === 'new' ? rows.length : 0, reviewing: 0, approved: current.status === 'approved' ? rows.length : 0, closed: 0 } } }).catch(() => {})
      }
      assert.equal(pathname, `/access-requests/${record.request_id}`)
      if (req.method() === 'GET') return route.fulfill({ json: current })
      assert.equal(req.method(), 'PATCH')
      const body = req.postDataJSON()
      patchCalls.push(body)
      assert.deepEqual(Object.keys(body).sort(), ['expected_version', 'notes', 'status'])
      if (patchCalls.length === 1) {
        current = { ...current, version: 2, notes: 'Saved by another reviewer.' }; rows = [current]
        return route.fulfill({ status: 409, json: { detail: 'This review changed. Reload before saving.' } })
      }
      assert.equal(body.expected_version, 2)
      current = { ...current, ...body, version: 3 }; rows = [current]
      return route.fulfill({ json: current })
    })
    await page.goto(`${origin}/review.html`)
    await page.getByLabel('Username or email').fill('test-admin')
    await page.getByLabel('Password', { exact: true }).fill('test-only-password')
    await page.getByRole('button', { name: 'Sign in to review' }).click()
    await page.locator('#login-error').waitFor({ state: 'visible' })
    assert.equal(await page.locator('#review-inbox').isVisible(), false)
    assert.equal(calls.filter(call => call.path === '/access-requests').length, 0)
    authRole = 'admin'
    await page.getByRole('button', { name: 'Sign in to review' }).click()
    await page.locator('#inbox-empty').waitFor({ state: 'visible' })
    rows = [current]
    await page.getByRole('button', { name: 'Refresh', exact: true }).click()
    await page.getByRole('button', { name: 'Review Example Grower Cooperative' }).click()
    await page.locator('#request-dialog').waitFor({ state: 'visible' })
    assert.equal(await page.locator('#detail-message img').count(), 0)
    assert.equal(await page.evaluate(() => Boolean(window.inquiryXss)), false)
    await page.getByLabel('Private review notes').fill('Unsaved discussion notes.')
    await page.keyboard.press('Escape')
    await page.getByRole('button', { name: 'Review Example Grower Cooperative' }).click()
    assert.equal(await page.getByLabel('Private review notes').inputValue(), 'Unsaved discussion notes.')
    for (let step = 0; step < 10; step += 1) {
      await page.keyboard.press('Tab')
      assert.equal(await page.evaluate(() => document.querySelector('#request-dialog').contains(document.activeElement)), true)
    }
    await page.getByLabel('Review status').selectOption('approved')
    await page.getByRole('button', { name: 'Save review' }).click()
    await page.locator('#detail-error').waitFor({ state: 'visible' })
    assert.equal(await page.getByLabel('Private review notes').inputValue(), 'Unsaved discussion notes.')
    await page.getByRole('button', { name: 'Load the latest saved review' }).click()
    await page.waitForFunction(() => document.querySelector('#detail-notes').value === 'Saved by another reviewer.')
    await page.getByLabel('Review status').selectOption('approved')
    await page.getByLabel('Private review notes').fill('Discussed scope and next onboarding step.')
    await page.setViewportSize({ width: 390, height: 844 })
    await page.screenshot({ path: path.join(output, 'review-mobile.png') })
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false)
    await page.getByRole('button', { name: 'Save review' }).click()
    await page.locator('#review-notice').waitFor({ state: 'visible' })
    await page.locator('#inbox-table-wrapper').waitFor({ state: 'visible' })
    await page.setViewportSize({ width: 1440, height: 1000 })
    await page.screenshot({ path: path.join(output, 'review-desktop.png'), fullPage: true })
    const started = new Promise(resolve => { listStarted = resolve })
    blockNextList = true
    await page.getByRole('button', { name: 'Refresh', exact: true }).click()
    await started
    await page.getByRole('button', { name: 'Sign out', exact: true }).click()
    releaseList()
    await page.locator('#review-login').waitFor({ state: 'visible' })
    assert.equal(await page.locator('#request-rows tr').count(), 0)
    assert.equal(await page.locator('#detail-message').textContent(), '')
    assert.equal(await page.evaluate(() => sessionStorage.getItem('mangopoint-request-review-token-v1')), null)
    assert.ok(calls.every(call => ['/auth/login', '/auth/me', '/access-requests', `/access-requests/${record.request_id}`].includes(call.path)))
    console.log('PASS: role restrictions, empty inbox, private notes, conflict recovery, safe text, keyboard focus, mobile review and logout during loading.')
    assert.deepEqual(errors, [])
  } finally { await context.close(); await browser.close() }
}

main().catch(error => { console.error(error.stack); process.exitCode = 1 })
