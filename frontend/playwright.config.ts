// End-to-end tests of the REAL running app (`npm run e2e`).
//
// Start the app first from the repository root: `python scripts/dev.py`
// (or `.venv\Scripts\python scripts\dev.py`). These tests talk to the real API,
// which talks to the real Bitbucket and (only when E2E_GEMINI=1) to Gemini.
// They use the locally installed Google Chrome, so no browser is downloaded.
//
// Output (screenshots, traces) may show real repository data; it is written
// to playwright-report/ and test-results/, which are git-ignored.
import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://127.0.0.1:5173',
    channel: 'chrome',
    headless: process.env.E2E_HEADED !== '1',
    viewport: { width: 1440, height: 1000 },
    screenshot: 'on',
    trace: 'retain-on-failure',
  },
})
