import { test, expect } from '@playwright/test'

// Isolated UI fixtures. No requests reach a real account or farm database.
async function openDashboard(page, { signIn = false, mapTiles = false } = {}) {
  const writes = []
  const user = { user_id: 'workspace-test', username: 'workspace-test', role: 'operator' }
  const session = () => ({ access_token: 'isolated-workspace-test', user,
    expires_at: new Date(Date.now() + 900000).toISOString() })
  if (!signIn) await page.addInitScript(() => sessionStorage.setItem('access_token', 'isolated-workspace-test'))
  await page.route('**/*', route => {
    const url = new URL(route.request().url())
    if (['127.0.0.1', 'localhost'].includes(url.hostname)) return route.continue()
    if (mapTiles && url.hostname.endsWith('arcgisonline.com')) return route.fulfill({
      contentType: 'image/png',
      body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64'),
    })
    return route.abort()
  })
  await page.route(/\/(health|auth|orchards|weather|monitoring|simulation|observations|alerts|sync|evaluation|validation)(\/|\?|$)/, async route => {
    const request = route.request(), path = new URL(request.url()).pathname
    if (path === '/auth/login' || path === '/auth/session/refresh') return route.fulfill({ json: session() })
    if (request.method() !== 'GET') {
      writes.push({ method: request.method(), path })
      return route.fulfill({ status: 400, json: { detail: 'No writes in workspace checks.' } })
    }
    if (path === '/health') return route.fulfill({ json: { status: 'healthy', database: 'connected' } })
    if (path === '/auth/me') return route.fulfill({ json: { user } })
    if (path === '/orchards') return route.fulfill({ json: { orchards: [] } })
    if (path === '/weather/live') return route.fulfill({ json: { current: {
      temperature_c: 27, humidity: 75, wind_speed_ms: 1, wind_direction_deg: 90, source: 'synthetic', cloud_cover_pct: 80,
    } } })
    if (path === '/simulation/runs') return route.fulfill({ json: { runs: [] } })
    if (path === '/alerts') return route.fulfill({ json: { alerts: [] } })
    if (path === '/observations/list') return route.fulfill({ json: { observations: [] } })
    return route.fulfill({ status: 503, json: { detail: 'Isolated workspace check.' } })
  })
  await page.goto(signIn ? '/login' : '/')
  if (signIn) {
    await page.getByLabel('Username or email').fill('workspace-test')
    await page.getByLabel('Password', { exact: true }).fill('isolated-test-password')
    await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  }
  await page.getByRole('button', { name: 'Maybe later', exact: true }).click()
  const connectionNotice = page.getByRole('button', { name: 'Close connection status', exact: true })
  if (await connectionNotice.isVisible()) await connectionNotice.click()
  return writes
}

const collapse = page => page.getByRole('button', { name: 'Collapse simulation workspace', exact: true })
const expand = page => page.getByRole('button', { name: 'Expand simulation workspace', exact: true })
const open = page => page.getByRole('button', { name: 'Open simulation workspace', exact: true })

test('signing in opens Setup with Orchard and Weather, before Simulate', async ({ page }, testInfo) => {
  const writes = await openDashboard(page, { signIn: true })
  await expect(page.locator('#sidebar-tab-setup')).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator('#sidebar-panel-setup')).toBeVisible()
  await expect(page.locator('#sidebar-panel-simulate')).toBeHidden()
  await expect(collapse(page)).toHaveAttribute('aria-expanded', 'true')
  await page.locator('#right-sidebar').screenshot({ path: testInfo.outputPath('setup-controls.png') })
  expect(writes).toEqual([])
})

test('desktop collapse frees map space, preserves inputs, restores focus and remembers the preference', async ({ page }, testInfo) => {
  const writes = await openDashboard(page)
  await page.locator('#sidebar-tab-simulate').click()
  await page.locator('#days-flowering').fill('75')
  const before = await page.locator('.fullscreen-map-area').boundingBox()
  await collapse(page).focus()
  await page.keyboard.press('Enter')
  await expect(expand(page)).toBeFocused()
  await expect(expand(page)).toHaveAttribute('aria-expanded', 'false')
  await expect.poll(async () => (await page.locator('.fullscreen-map-area').boundingBox()).width).toBeGreaterThan(before.width + 200)
  await page.screenshot({ path: testInfo.outputPath('collapsed-controls.png') })
  await page.keyboard.press('Enter')
  await expect(page.locator('#sidebar-tab-simulate')).toBeFocused()
  await expect(page.locator('#days-flowering')).toHaveValue('75')
  await collapse(page).click()
  await page.getByRole('button', { name: 'Open Setup', exact: true }).click()
  await expect(page.locator('#sidebar-tab-setup')).toHaveAttribute('aria-selected', 'true')
  await collapse(page).click()
  await expect.poll(() => page.evaluate(() => localStorage.getItem('mangopoint.sidebarCollapsed.v1'))).toBe('true')
  await page.reload()
  await expect(expand(page)).toBeVisible()
  await expand(page).click()
  await expect(page.locator('#sidebar-tab-setup')).toHaveAttribute('aria-selected', 'true')
  expect(writes).toEqual([])
})

test('mobile heading collapses the drawer and reopening preserves the selected workflow and inputs', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const writes = await openDashboard(page)
  await expect(page.locator('#right-sidebar')).toHaveAttribute('inert', '')
  await open(page).click()
  await expect(page.locator('#sidebar-tab-setup')).toHaveAttribute('aria-selected', 'true')
  await page.locator('#sidebar-tab-simulate').click()
  await page.locator('#days-flowering').fill('75')
  await collapse(page).click()
  await expect(page.locator('#right-sidebar')).toHaveAttribute('inert', '')
  await expect(open(page)).toBeFocused()
  await open(page).click()
  await expect(page.locator('#sidebar-tab-simulate')).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator('#days-flowering')).toHaveValue('75')
  await page.keyboard.press('Escape')
  await expect(open(page)).toBeFocused()
  await open(page).click()
  await page.locator('.sidebar-mobile-close').click()
  await expect(page.locator('#right-sidebar')).toHaveAttribute('aria-hidden', 'true')
  expect(writes).toEqual([])
})

test('resizing an open mobile drawer restores desktop scrolling and collapse controls', async ({ page }) => {
  const writes = await openDashboard(page)
  await collapse(page).click()
  await page.setViewportSize({ width: 820, height: 900 })
  await open(page).click()
  await expect.poll(() => page.evaluate(() => document.body.style.overflow)).toBe('hidden')
  await page.setViewportSize({ width: 1440, height: 960 })
  await expect.poll(() => page.evaluate(() => document.body.style.overflow)).not.toBe('hidden')
  await expect(expand(page)).toBeVisible()
  await expand(page).click()
  await expect(collapse(page)).toBeVisible()
  await expect(page.locator('#sidebar-panel-setup')).toBeVisible()
  expect(writes).toEqual([])
})

test('collapse and expand keep the map painted through animated canvas resizes', async ({ page }, testInfo) => {
  // Sample after a drawing-buffer resize, before browser paint. A resize must
  // redraw synchronously; an async repaint leaves a transparent/blank frame.
  await page.addInitScript(() => {
    window.mapResizeFrames = { armed: false, samples: [] }
    for (const property of ['width', 'height']) {
      const descriptor = Object.getOwnPropertyDescriptor(HTMLCanvasElement.prototype, property)
      Object.defineProperty(HTMLCanvasElement.prototype, property, {
        ...descriptor,
        set(value) {
          descriptor.set.call(this, value)
          if (!window.mapResizeFrames.armed || !this.classList.contains('maplibregl-canvas')) return
          queueMicrotask(() => {
            const gl = this.getContext('webgl2') || this.getContext('webgl')
            if (!gl || !window.mapResizeFrames.armed) return
            const pixel = new Uint8Array(4)
            gl.readPixels(Math.floor(this.width / 2), Math.floor(this.height / 2), 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, pixel)
            window.mapResizeFrames.samples.push({ width: this.width, alpha: pixel[3] })
          })
        },
      })
    }
  })
  const writes = await openDashboard(page, { mapTiles: true })
  const marker = page.getByRole('button', { name: 'Tree 1', exact: true })
  let previous = '', stable = 0
  await expect.poll(async () => {
    const box = await marker.boundingBox()
    const position = box ? `${box.x.toFixed(1)}:${box.y.toFixed(1)}` : ''
    stable = position && position === previous ? stable + 1 : 0
    previous = position
    return stable
  }, { intervals: [100], timeout: 10000 }).toBeGreaterThanOrEqual(5)
  const width = (await page.locator('.fullscreen-map-area').boundingBox()).width
  const canvas = await page.locator('.maplibregl-canvas').elementHandle()
  await page.evaluate(() => { window.mapResizeFrames.armed = true })
  await collapse(page).click()
  await expect.poll(async () => (await page.locator('.fullscreen-map-area').boundingBox()).width).toBeGreaterThan(width + 280)
  await expand(page).click()
  await expect.poll(async () => (await page.locator('.fullscreen-map-area').boundingBox()).width).toBe(width)
  const samples = await page.evaluate(() => {
    window.mapResizeFrames.armed = false
    return window.mapResizeFrames.samples
  })
  await testInfo.attach('canvas-resize-frames.json', { body: Buffer.from(JSON.stringify(samples)), contentType: 'application/json' })
  expect(samples.length).toBeGreaterThan(0)
  expect(samples.filter(sample => sample.alpha === 0)).toEqual([])
  expect(await canvas.evaluate(element => element.isConnected && element === document.querySelector('.maplibregl-canvas'))).toBe(true)
  expect(writes).toEqual([])
})
