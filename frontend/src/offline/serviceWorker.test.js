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
