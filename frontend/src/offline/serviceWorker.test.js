import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'

test('the PWA never intercepts or caches API responses, including collection URLs', () => {
  const handlers = {}
  const self = {
    location: { origin: 'https://mango-point-projects.vercel.app' },
    addEventListener: (name, handler) => { handlers[name] = handler },
  }
  vm.runInNewContext(readFileSync(new URL('../../public/sw.js', import.meta.url), 'utf8'), { self, URL })
  for (const path of ['/api/health', '/api/auth/me', '/api/orchards', '/api/simulation/runs', '/orchards', '/alerts', '/health', '/sync/status']) {
    let intercepted = false
    handlers.fetch({
      request: { method: 'GET', url: `${self.location.origin}${path}` },
      respondWith: () => { intercepted = true },
    })
    assert.equal(intercepted, false, `${path} must go directly to the server`)
  }
})

test('install precaches the local PDF engine asset without waiting for large orchard imagery', async () => {
  const handlers = {}, fetched = []
  const self = { addEventListener: (name, handler) => { handlers[name] = handler }, skipWaiting: async () => {} }
  const fetch = async (path) => {
    fetched.push(path)
    return path === '/.vite/manifest.json'
      ? new Response(JSON.stringify({ report: { file: 'assets/report.js',
        assets: ['assets/html2pdf.bundle.min.js', 'assets/font.woff2', 'assets/orchard.png'] },
        orchard: { file: 'assets/orchard.png' } }))
      : new Response('fixture asset')
  }
  vm.runInNewContext(readFileSync(new URL('../../public/sw.js', import.meta.url), 'utf8'), {
    self, fetch, caches: { open: async () => ({ put: async () => {} }) },
  })
  let installed
  handlers.install({ waitUntil: (pending) => { installed = pending } })
  await installed
  assert.ok(fetched.includes('/assets/html2pdf.bundle.min.js'))
  assert.ok(fetched.includes('/assets/report.js'))
  assert.ok(fetched.includes('/assets/font.woff2'))
  assert.ok(!fetched.includes('/assets/orchard.png'))
})

test('online shell requests bypass stale HTTP/cache-storage releases and remain available offline', async () => {
  for (const path of ['/login', '/index.html', '/.vite/manifest.json']) {
    const handlers = {}, stored = new Map(), origin = 'https://mango-point-projects.vercel.app'
    const request = { method: 'GET', mode: path === '/login' ? 'navigate' : 'cors', url: origin + path }
    const cacheKey = path === '/login' ? '/index.html' : path
    stored.set(cacheKey, new Response('previous release'))
    let offline = false
    vm.runInNewContext(readFileSync(new URL('../../public/sw.js', import.meta.url), 'utf8'), {
      self: { location: { origin }, addEventListener: (name, handler) => { handlers[name] = handler } }, URL,
      fetch: async (_request, options) => {
        if (offline) throw new Error('offline')
        return new Response(options?.cache === 'no-store' ? 'current release' : 'previous release')
      },
      caches: {
        open: async () => ({ put: async (key, response) => stored.set(typeof key === 'string' ? key : new URL(key.url).pathname, response) }),
        match: async (key) => stored.get(typeof key === 'string' ? key : new URL(key.url).pathname)?.clone(),
      },
    })
    let response
    const dispatch = () => handlers.fetch({ request, respondWith: (pending) => { response = pending } })
    dispatch()
    assert.equal(await (await response).text(), 'current release', path)
    offline = true
    dispatch()
    assert.equal(await (await response).text(), 'current release', `${path} offline fallback`)
  }
})

test('activating a release clears only older MangoPoint app caches', async () => {
  const handlers = {}, deleted = []
  let claimed = false, activated
  vm.runInNewContext(readFileSync(new URL('../../public/sw.js', import.meta.url), 'utf8'), {
    self: { addEventListener: (name, handler) => { handlers[name] = handler },
      clients: { claim: async () => { claimed = true } } },
    caches: { keys: async () => ['mangopoint-app-v5', 'mangopoint-app-v6', 'unrelated-local-cache'],
      delete: async (key) => { deleted.push(key) } },
  })
  handlers.activate({ waitUntil: (pending) => { activated = pending } })
  await activated
  assert.deepEqual(deleted, ['mangopoint-app-v5'])
  assert.equal(claimed, true)
})

test('a failed release download cannot replace the working offline shell', async () => {
  const handlers = {}, written = []
  let activated = false, installed
  vm.runInNewContext(readFileSync(new URL('../../public/sw.js', import.meta.url), 'utf8'), {
    self: { addEventListener: (name, handler) => { handlers[name] = handler }, skipWaiting: async () => { activated = true } },
    fetch: async (asset) => asset === '/.vite/manifest.json'
      ? { ok: true, json: async () => ({ app: { file: 'assets/current.js' } }) }
      : new Response('fixture asset', { status: asset === '/assets/current.js' ? 503 : 200 }),
    caches: { open: async () => ({ put: async (asset) => { written.push(asset) } }) },
  })
  handlers.install({ waitUntil: (pending) => { installed = pending } })
  await assert.rejects(installed, /current.js is unavailable/)
  assert.deepEqual(written, [])
  assert.equal(activated, false)
})

test('a failed response body cannot install a partial offline release', async () => {
  const handlers = {}, written = []
  let activated = false, installed
  vm.runInNewContext(readFileSync(new URL('../../public/sw.js', import.meta.url), 'utf8'), {
    self: { addEventListener: (name, handler) => { handlers[name] = handler }, skipWaiting: async () => { activated = true } },
    fetch: async (asset) => asset === '/.vite/manifest.json'
      ? new Response(JSON.stringify({ app: { file: 'assets/interrupted.js' } }))
      : asset === '/assets/interrupted.js'
        ? new Response(new ReadableStream({ pull(controller) { controller.error(new Error('Download interrupted')) } }))
        : new Response('fixture asset'),
    caches: { open: async () => ({ put: async (asset) => { written.push(asset) } }) },
  })
  handlers.install({ waitUntil: (pending) => { installed = pending } })
  await assert.rejects(installed, /Download interrupted/)
  assert.deepEqual(written, [])
  assert.equal(activated, false)
})
