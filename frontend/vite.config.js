import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'

// Change the worker whenever the built assets change, so an existing PWA
// installs the new shell and all its offline dependencies on the next visit.
function releaseServiceWorker() {
  return {
    name: 'mangopoint-release-service-worker',
    apply: 'build',
    generateBundle(_options, bundle) {
      const template = readFileSync(new URL('./public/sw.js', import.meta.url), 'utf8')
      const release = createHash('sha256').update(template)
        .update(Object.keys(bundle).sort().join('\n')).digest('hex').slice(0, 12)
      this.emitFile({ type: 'asset', fileName: 'sw.js',
        source: template.replace('mangopoint-app-v6', `mangopoint-app-v6-${release}`) })
    },
  }
}

export default defineConfig({
  plugins: [react(), releaseServiceWorker()],
  build: {
    manifest: true,
  },
  resolve: {
    dedupe: ['react', 'react-dom'],
  },
  server: {
    port: 3000,
    proxy: {
      '/auth': { target: 'http://localhost:8000', changeOrigin: true },
      '/orchards': { target: 'http://localhost:8000', changeOrigin: true },
      '/simulation': { target: 'http://localhost:8000', changeOrigin: true },
      '/monitoring': { target: 'http://localhost:8000', changeOrigin: true },
      '/alerts': { target: 'http://localhost:8000', changeOrigin: true },
      '/observations': { target: 'http://localhost:8000', changeOrigin: true },
      '/evaluation': { target: 'http://localhost:8000', changeOrigin: true },
      '/validation': { target: 'http://localhost:8000', changeOrigin: true },
      '/weather': { target: 'http://localhost:8000', changeOrigin: true },
      '/sync': { target: 'http://localhost:8000', changeOrigin: true },
    }
  }
})
