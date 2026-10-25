const CACHE_VERSION = 'mangopoint-app-v22'
const CORE_ASSETS = [
  '/',
  '/index.html',
  '/manifest.webmanifest',
  '/brand/mangopoint-logo-v3.png',
  '/trees.geojson',
]

async function buildAssets() {
  try {
    const response = await fetch('/.vite/manifest.json', { cache: 'no-store' })
    if (!response.ok) return []
    const manifest = await response.json()
    const assets = new Set()
    for (const entry of Object.values(manifest)) {
      if (entry.file) assets.add(`/${entry.file}`)
      for (const css of entry.css || []) assets.add(`/${css}`)
      // Large orchard imagery is cached when the signed-in dashboard loads it.
      // Holding service-worker activation for multi-megabyte images makes the
      // first offline-ready install unreliable on slower connections.
      for (const asset of entry.assets || []) {
        if (/\.(?:js|woff2?|ttf|otf)$/i.test(asset)) assets.add(`/${asset}`)
      }
    }
    return [...assets]
  } catch (_) {
    return []
  }
}

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_VERSION)
    const assets = [...CORE_ASSETS, ...(await buildAssets())]
    await Promise.allSettled(assets.map(async (asset) => {
      const response = await fetch(asset, { cache: 'reload' })
      if (response.ok) await cache.put(asset, response)
    }))
    await self.skipWaiting()
  })())
})

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys()
    await Promise.all(keys.filter((key) => key !== CACHE_VERSION).map((key) => caches.delete(key)))
    await self.clients.claim()
  })())
})

function isApiRequest(url) {
  return [
    '/api', '/auth', '/orchards', '/simulation', '/monitoring', '/alerts',
    '/observations', '/evaluation', '/validation', '/weather', '/sync', '/health',
  ].some((prefix) => url.pathname === prefix || url.pathname.startsWith(`${prefix}/`))
}

self.addEventListener('fetch', (event) => {
  const request = event.request
  if (request.method !== 'GET') return

  const url = new URL(request.url)
  if (url.origin !== self.location.origin || isApiRequest(url)) return

  if (request.mode === 'navigate') {
    event.respondWith((async () => {
      try {
        const response = await fetch(request)
        const cache = await caches.open(CACHE_VERSION)
        if (response.ok) await cache.put('/index.html', response.clone())
        return response
      } catch (_) {
        return (await caches.match('/index.html', { ignoreVary: true }))
          || (await caches.match('/', { ignoreVary: true }))
      }
    })())
    return
  }

  event.respondWith((async () => {
    // Install-time requests and browser subresource requests can carry
    // different Origin/Accept headers. The URL identifies immutable Vite
    // assets, so Vary must not prevent a valid precache hit while offline.
    const cached = await caches.match(request, { ignoreVary: true })
    if (cached) return cached
    const response = await fetch(request)
    if (response.ok) {
      const cache = await caches.open(CACHE_VERSION)
      await cache.put(request, response.clone())
    }
    return response
  })())
})
