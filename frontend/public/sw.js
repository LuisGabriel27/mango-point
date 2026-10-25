const CACHE_VERSION = 'mangopoint-app-v6'
const CORE_ASSETS = [
  '/',
  '/index.html',
  '/manifest.webmanifest',
  '/brand/mangopoint-logo-v3.png',
  '/trees.geojson',
]

async function buildAssets() {
  const response = await fetch('/.vite/manifest.json', { cache: 'no-store' })
  if (!response.ok) throw new Error('The app manifest is unavailable.')
  const manifest = await response.json()
  const assets = new Set()
  for (const entry of Object.values(manifest)) {
    if (entry.file && /\.(?:js|css|woff2?|ttf|otf)$/i.test(entry.file)) assets.add(`/${entry.file}`)
    for (const css of entry.css || []) assets.add(`/${css}`)
    // Large orchard imagery is cached when the signed-in dashboard loads it.
    // Holding service-worker activation for multi-megabyte images makes the
    // first offline-ready install unreliable on slower connections.
    for (const asset of entry.assets || []) {
      if (/\.(?:js|woff2?|ttf|otf)$/i.test(asset)) assets.add(`/${asset}`)
    }
  }
  return [...assets]
}

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    // A partial download must leave the previous worker and offline shell in
    // place. Publish the new HTML only after its dependencies are cached.
    const assets = [...new Set([...CORE_ASSETS, ...(await buildAssets())])]
    const downloaded = await Promise.all(assets.map(async (asset) => {
      const response = await fetch(asset, { cache: 'reload' })
      if (!response.ok) throw new Error(`The app asset ${asset} is unavailable.`)
      // Finish reading each download before waiting for the remaining headers.
      // Otherwise large unread bodies can occupy every connection and stall
      // queued assets. Keep the original response for the atomic cache write.
      await response.clone().blob()
      return [asset, response]
    }))
    const cache = await caches.open(CACHE_VERSION)
    const html = (asset) => asset === '/' || asset === '/index.html'
    try {
      await Promise.all(downloaded.filter(([asset]) => !html(asset)).map(([asset, response]) => cache.put(asset, response)))
      await Promise.all(downloaded.filter(([asset]) => html(asset)).map(([asset, response]) => cache.put(asset, response)))
    } catch (error) {
      await caches.delete(CACHE_VERSION)
      throw error
    }
    await self.skipWaiting()
  })())
})

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys()
    await Promise.all(keys.filter((key) => key.startsWith('mangopoint-app-') && key !== CACHE_VERSION)
      .map((key) => caches.delete(key)))
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

  const navigation = request.mode === 'navigate'
  const shellRequest = ['/', '/index.html', '/.vite/manifest.json', '/manifest.webmanifest'].includes(url.pathname)
  if (navigation || shellRequest) {
    event.respondWith((async () => {
      try {
        // An online navigation must discover the latest HTML and hashed bundle,
        // even when an earlier release left a fresh response in the HTTP cache.
        const response = await fetch(request, { cache: 'no-store' })
        const cache = await caches.open(CACHE_VERSION)
        if (response.ok) await cache.put(navigation ? '/index.html' : request, response.clone())
        return response
      } catch (_) {
        return navigation
          ? (await caches.match('/index.html', { ignoreVary: true })) || (await caches.match('/', { ignoreVary: true }))
          : await caches.match(request, { ignoreVary: true })
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
