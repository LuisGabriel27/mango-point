import { expect, test } from '@playwright/test'
import { createServer } from 'node:http'
import { readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

// Isolated older-release fixture. All auth/health requests are intercepted;
// this server never uses real accounts, mail or orchard records.
test('a previously cached login upgrades to recovery controls and keeps the new shell offline', async ({ context, page }, testInfo) => {
  const dist = fileURLToPath(new URL('../dist/', import.meta.url))
  let previousRelease = true
  const previousHtml = '<!doctype html><h1>Previous login release</h1><script>navigator.serviceWorker.register("/sw.js", {updateViaCache:"none"})</script>'
  const previousWorker = `
    const cacheName = 'mangopoint-app-v5';
    self.addEventListener('install', e => e.waitUntil((async () => {
      const cache = await caches.open(cacheName);
      await cache.put('/index.html', new Response(${JSON.stringify(previousHtml)}, {headers:{'Content-Type':'text/html'}}));
      await self.skipWaiting();
    })()));
    self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
    self.addEventListener('fetch', e => {
      if (e.request.mode === 'navigate') e.respondWith(fetch(e.request).catch(() => caches.match('/index.html')));
    });`
  const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json',
    '.webmanifest': 'application/manifest+json', '.png': 'image/png', '.woff2': 'font/woff2', '.svg': 'image/svg+xml' }
  const server = createServer(async (request, response) => {
    try {
      const pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname)
      response.setHeader('Cache-Control', previousRelease && pathname === '/login' ? 'public, max-age=31536000' : 'no-store')
      if (previousRelease && pathname === '/sw.js') {
        response.setHeader('Content-Type', 'text/javascript')
        return response.end(previousWorker)
      }
      if (previousRelease && ['/', '/index.html', '/login'].includes(pathname)) {
        response.setHeader('Content-Type', 'text/html')
        return response.end(previousHtml)
      }
      const relative = ['/', '/login'].includes(pathname) ? 'index.html' : pathname.slice(1)
      const file = path.resolve(dist, relative)
      if (!file.startsWith(dist)) { response.writeHead(403); return response.end() }
      response.setHeader('Content-Type', types[path.extname(file)] || 'application/octet-stream')
      response.end(await readFile(file))
    } catch { response.writeHead(404); response.end() }
  })
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve))
  const origin = `http://127.0.0.1:${server.address().port}`
  let recoveryRequests = 0
  try {
    await page.route(/\/(health|auth)(\/|\?|$)/, async (route) => {
      const pathname = new URL(route.request().url()).pathname
      if (pathname.endsWith('/health')) return route.fulfill({ json: { status: 'healthy', database: 'connected' } })
      if (route.request().postDataJSON()?.recover_sessions) recoveryRequests++
      return route.fulfill({ status: 409, json: { detail: 'This account already has two active sessions.' } })
    })
    await page.goto(origin + '/login')
    await expect(page.getByRole('heading', { name: 'Previous login release' })).toBeVisible()
    await page.waitForFunction(() => Boolean(navigator.serviceWorker.controller))
    await page.evaluate(async () => {
      sessionStorage.setItem('upgrade-sentinel', 'keep')
      const database = await new Promise((resolve, reject) => {
        const request = indexedDB.open('isolated-upgrade-sentinel', 1)
        request.onupgradeneeded = () => request.result.createObjectStore('draft')
        request.onerror = () => reject(request.error)
        request.onsuccess = () => resolve(request.result)
      })
      await new Promise((resolve, reject) => {
        const transaction = database.transaction('draft', 'readwrite')
        transaction.objectStore('draft').put('keep', 'draft')
        transaction.oncomplete = resolve
        transaction.onerror = () => reject(transaction.error)
      })
      database.close()
    })
    previousRelease = false
    await page.evaluate(async () => {
      const registration = await navigator.serviceWorker.ready
      await registration.update()
      const worker = registration.installing || registration.waiting
      if (worker && worker.state !== 'activated') {
        await new Promise((resolve, reject) => {
          const timeout = setTimeout(() => reject(new Error(`Update worker remained ${worker.state}.`)), 30_000)
          worker.addEventListener('statechange', () => {
            if (worker.state === 'activated') { clearTimeout(timeout); resolve() }
            else if (worker.state === 'redundant') { clearTimeout(timeout); reject(new Error('Update worker became redundant.')) }
          })
        })
      }
    })
    await expect.poll(() => page.evaluate(async () => (await caches.keys()).some((key) => /^mangopoint-app-v6-[a-f0-9]{12}$/.test(key))),
      { timeout: 30_000 }).toBe(true)
    await expect.poll(() => page.evaluate(async () => (await caches.keys()).includes('mangopoint-app-v5')),
      { timeout: 30_000 }).toBe(false)
    // Updating a worker must not force a reload over a user's current inputs.
    await expect(page.getByRole('heading', { name: 'Previous login release' })).toBeVisible()
    await page.goto(origin + '/login')
    await expect(page.getByRole('button', { name: 'Recover account access', exact: true })).toBeVisible()
    await page.getByLabel('Username or email').fill('upgrade-fixture')
    await page.getByLabel('Password', { exact: true }).fill('synthetic-fixture-password')
    await page.getByRole('button', { name: 'Sign in', exact: true }).click()
    await expect(page.getByRole('alertdialog', { name: 'Two sessions are active', exact: true })).toBeVisible()
    await page.screenshot({ path: testInfo.outputPath('upgraded-recovery-modal.png') })
    await page.getByRole('button', { name: 'Cancel', exact: true }).click()
    expect(recoveryRequests).toBe(0)
    expect(await page.evaluate(() => sessionStorage.getItem('upgrade-sentinel'))).toBe('keep')
    expect(await page.evaluate(async () => new Promise((resolve, reject) => {
      const request = indexedDB.open('isolated-upgrade-sentinel')
      request.onerror = () => reject(request.error)
      request.onsuccess = () => {
        const database = request.result
        const read = database.transaction('draft').objectStore('draft').get('draft')
        read.onsuccess = () => { resolve(read.result); database.close() }
        read.onerror = () => reject(read.error)
      }
    }))).toBe('keep')
    await context.setOffline(true)
    await page.reload({ waitUntil: 'domcontentloaded' })
    await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Recover account access', exact: true })).toBeVisible()
  } finally {
    await context.close()
    await new Promise((resolve) => { server.close(resolve); server.closeAllConnections() })
  }
})
