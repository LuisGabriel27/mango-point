import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests', testMatch: '*.spec.js', workers: 1, timeout: 60000,
  outputDir: '../outputs/tutorial-browser/artifacts',
  reporter: [['list'], ['json', { outputFile: '../outputs/tutorial-browser/results.json' }]],
  use: {
    baseURL: 'http://127.0.0.1:3011', browserName: 'chromium',
    channel: process.env.PLAYWRIGHT_CHANNEL || 'msedge',
    headless: true, viewport: { width: 1440, height: 960 },
    screenshot: 'only-on-failure', trace: 'retain-on-failure',
  },
  webServer: {
    command: 'npm.cmd run dev -- --host 127.0.0.1 --port 3011 --strictPort',
    url: 'http://127.0.0.1:3011', reuseExistingServer: !process.env.CI,
  },
})
