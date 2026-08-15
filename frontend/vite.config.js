import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
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
