import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  testMatch: 'production-connection.spec.js',
  workers: 1,
  timeout: 90_000,
  outputDir: '../outputs/production-connection-browser/artifacts',
  reporter: [['list']],
  use: {
    baseURL: 'https://mango-point-projects.vercel.app',
    browserName: 'chromium',
    channel: process.env.PLAYWRIGHT_CHANNEL || 'msedge',
    headless: true,
    viewport: { width: 1280, height: 800 },
    // Auth credentials and tokens must never be written to traces/screenshots.
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
})
