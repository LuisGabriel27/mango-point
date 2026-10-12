import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  testMatch: 'offline-api-connection.spec.js',
  workers: 1,
  timeout: 90_000,
  outputDir: '../outputs/offline-companion-api-browser/artifacts',
  reporter: [['list']],
  use: {
    baseURL: 'https://mango-point-projects.vercel.app',
    browserName: 'chromium',
    channel: process.env.PLAYWRIGHT_CHANNEL || 'msedge',
    permissions: ['local-network-access'],
    headless: true,
    viewport: { width: 1280, height: 800 },
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
})
