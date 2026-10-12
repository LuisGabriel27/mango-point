import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  testMatch: 'live-local-first.spec.js',
  workers: 1,
  timeout: 60_000,
  outputDir: '../outputs/live-local-first-browser/artifacts',
  reporter: [['list']],
  use: {
    baseURL: 'https://mango-point-projects.vercel.app',
    browserName: 'chromium',
    channel: process.env.PLAYWRIGHT_CHANNEL || 'msedge',
    permissions: ['local-network-access'],
    headless: true,
    viewport: { width: 1280, height: 800 },
    trace: 'retain-on-failure',
  },
})
