// End-to-end checks of the running ShipSafe app in live (Bitbucket) mode.
//
// Default run: reads only. Nothing is scanned and nothing is sent to an AI model.
// Opt-in, with environment variables:
//   E2E_PR_REPO=<slug> E2E_PR_ID=<id>  scan that pull request (read-only on Bitbucket;
//                                       the scan is stored in the local database)
//   E2E_EXPECT_FINDINGS=1              also require the scan to have static findings
//   E2E_AI=1                           also confirm sharing and send that scan to the first configured
//                                       AI model (OpenAI preferred). Only for code you may share with it.
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const API = process.env.E2E_API_URL ?? 'http://127.0.0.1:8000'
const PR_REPO = process.env.E2E_PR_REPO
const PR_ID = process.env.E2E_PR_ID
/** Real Bitbucket answers can take 5–15 s per page; every Bitbucket-backed wait gets this budget. */
const BITBUCKET_WAIT = 60_000
const DEMO_TEXT =['LedgerLite', 'LOCAL DEMO', 'LIVE DEMO', 'ShipSafe Demo', 'Synthetic demo repository']

interface BitbucketStatus { configured: boolean; workspace: string | null; repositories: string[] }
interface AIProvider { provider: string; label: string; configured: boolean; model: string | null }

let bitbucket: BitbucketStatus
let providers: AIProvider[]
const configured = () => providers.filter(item => item.configured)

test.beforeAll(async ({ request }) => {
  const health = await request.get(`${API}/api/health`).catch(() => null)
  expect(health?.ok(), `The API is not running at ${API}. Start the app first: python scripts/dev.py`).toBeTruthy()
  bitbucket = await (await request.get(`${API}/api/bitbucket/status`)).json()
  providers = await (await request.get(`${API}/api/ai/providers`)).json()
  expect(bitbucket.configured, 'These tests need SHIPSAFE_BITBUCKET_* configured on the API server').toBe(true)
})

/** Console errors other than the browser's automatic favicon request. */
function collectErrors(page: Page) {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(String(error)))
  page.on('response', response => {
    if (response.status() >= 400 && !response.url().endsWith('/favicon.ico')) errors.push(`HTTP ${response.status()} ${response.url()}`)
  })
  return errors
}

const primaryNav = (page: Page) => page.getByRole('navigation', { name: 'Primary navigation' })
const bitbucketNav = (page: Page) => page.getByRole('navigation', { name: 'Bitbucket navigation' })

async function expectNoDemoText(page: Page) {
  const text = await page.locator('body').innerText()
  for (const item of DEMO_TEXT) expect(text, `demo label "${item}" is visible`).not.toContain(item)
}

async function openApp(page: Page) {
  await page.goto('/')
  await expect(page.getByText('BITBUCKET · READ-ONLY')).toBeVisible()
}

test('overview runs in live Bitbucket mode without demo data', async ({ page }) => {
  const errors = collectErrors(page)
  await openApp(page)
  await expect(page.getByRole('region', { name: 'Analyze a pull request' })).toBeVisible()
  await expect(page.locator('.workspace-picker')).toContainText('Bitbucket')
  await expect(page.locator('.sidebar-footer')).toContainText('API connected')
  await expectNoDemoText(page)
  expect(errors).toEqual([])
})

test('repositories page lists the approved repositories from Bitbucket', async ({ page }) => {
  await openApp(page)
  await bitbucketNav(page).getByRole('button', { name: 'Repositories' }).click()
  const section = page.getByRole('region', { name: 'Bitbucket' })
  for (const slug of bitbucket.repositories) await expect(section.getByText(`${bitbucket.workspace}/${slug}`).first()).toBeVisible({ timeout: BITBUCKET_WAIT })
})

test('pull requests load from Bitbucket and one opens in PR analysis', async ({ page }) => {
  const errors = collectErrors(page)
  await openApp(page)
  await page.getByRole('region', { name: 'Analyze a pull request' }).getByRole('button', { name: /Choose a pull request/ }).click()
  await expect(page.locator('.topbar-left strong')).toHaveText('Pull requests')
  const section = page.getByRole('region', { name: 'Bitbucket' })
  const analyze = section.getByRole('button', { name: /Analyze pull request/ })
  const empty = section.getByRole('heading', { name: /^No / })
  await expect(analyze.first().or(empty)).toBeVisible({ timeout: BITBUCKET_WAIT })
  if (await analyze.count() === 0) test.skip(true, 'No open pull request in the approved repositories')
  await analyze.first().click()
  await expect(page.locator('.topbar-left strong')).toHaveText('PR analysis')
  await expect(section.getByRole('button', { name: /Scan this pull request/ }).or(section.getByText(/cannot be scanned|not scannable/i)).first()).toBeVisible({ timeout: BITBUCKET_WAIT })
  expect(errors).toEqual([])
})

test('scan history lists only Bitbucket pull request scans', async ({ page }) => {
  await openApp(page)
  await primaryNav(page).getByRole('button', { name: /Scan history/ }).click()
  await expect(page.getByRole('heading', { name: 'Recent analyses' })).toBeVisible()
  const rows = page.locator('.history-table tbody tr')
  const count = await rows.count()
  for (let index = 0; index < count; index++) await expect(rows.nth(index)).toContainText(/Bitbucket · .+ · PR #/)
  await expectNoDemoText(page)
})

test('configuration shows Bitbucket and the configured AI models', async ({ page }) => {
  await openApp(page)
  await page.getByRole('button', { name: 'Configuration' }).click()
  await expect(page.getByText(`Bitbucket · ${bitbucket.workspace}`, { exact: true })).toBeVisible()
  await expect(page.getByText(bitbucket.repositories.join(', '), { exact: true })).toBeVisible()
  if (configured().length) for (const item of configured()) await expect(page.getByText(`${item.label} · ${item.model}`, { exact: true })).toBeVisible()
  else await expect(page.getByText('Not configured')).toBeVisible()
})

test('AI model panel: model shown, and non-demo code cannot be sent without confirmation', async ({ page }) => {
  await openApp(page)
  if (await page.getByRole('heading', { name: 'No pull request scanned yet' }).isVisible()) test.skip(true, 'No pull request scan stored yet')
  await primaryNav(page).getByRole('button', { name: /Claude Review/ }).click()
  const panel = page.getByRole('region', { name: 'Review with an AI model' })
  await expect(panel).toBeVisible()
  if (!configured().length) {
    await expect(panel.getByText(/No AI model is configured/)).toBeVisible()
    return
  }
  const first = configured().find(item => item.provider === 'openai') ?? configured()[0]
  await expect(panel).toContainText(first.model ?? '')
  const run = panel.getByRole('button', { name: new RegExp(`Run ${first.label} review`) })
  await expect(run).toBeDisabled()   // a pull request scan is never the synthetic demo
  await panel.getByRole('checkbox').check()
  await expect(run).toBeEnabled()
  await panel.getByRole('checkbox').uncheck()   // nothing is sent in the default run
  await expect(run).toBeDisabled()
})

test.describe('opt-in: scan a pull request (and review it with an AI model)', () => {
  test.skip(!PR_REPO || !PR_ID, 'Set E2E_PR_REPO and E2E_PR_ID to scan a pull request')

  test('scan → report → dashboard → AI model review', async ({ page }) => {
    test.setTimeout(240_000)
    const errors = collectErrors(page)
    await openApp(page)
    await bitbucketNav(page).getByRole('button', { name: 'Pull requests' }).click()
    const section = page.getByRole('region', { name: 'Bitbucket' })
    await section.getByRole('combobox', { name: 'Repository' }).selectOption({ label: `${bitbucket.workspace}/${PR_REPO}` }, { timeout: BITBUCKET_WAIT })
    await section.getByRole('button', { name: new RegExp(`Analyze pull request ${PR_ID}\\b`) }).click({ timeout: BITBUCKET_WAIT })
    await section.getByRole('button', { name: /Scan this pull request/ }).click({ timeout: BITBUCKET_WAIT })
    const report = section.getByRole('region', { name: 'Scan report' })
    await expect(report).toBeVisible({ timeout: 120_000 })
    if (process.env.E2E_EXPECT_FINDINGS === '1') await expect(report.getByRole('heading', { name: 'No risk patterns detected' })).toHaveCount(0)
    await page.screenshot({ path: test.info().outputPath('pr-scan-report.png'), fullPage: true })

    await report.getByRole('button', { name: /Open in dashboard/ }).click()
    await expect(page.getByRole('heading', { name: 'Release overview' })).toBeVisible()
    await expect(page.getByRole('region', { name: 'Scan source' })).toContainText(`#${PR_ID}`)
    await expectNoDemoText(page)

    if (process.env.E2E_AI === '1') {
      expect(configured().length, 'E2E_AI=1 needs SHIPSAFE_OPENAI_API_KEY or SHIPSAFE_GEMINI_API_KEY on the API server').toBeGreaterThan(0)
      await primaryNav(page).getByRole('button', { name: /Claude Review/ }).click()
      const panel = page.getByRole('region', { name: 'Review with an AI model' })
      await panel.getByRole('checkbox').check()   // the person running E2E_AI=1 confirms sharing
      await panel.getByRole('button', { name: /Run .* review/ }).click()
      await expect(panel.getByRole('status').or(panel.getByRole('alert'))).toBeVisible({ timeout: 300_000 })
      await expect(panel.getByRole('alert'), 'AI review failed').toHaveCount(0)
      await expect(page.getByText(/Generated by /)).toBeVisible()
      await page.screenshot({ path: test.info().outputPath('ai-review.png'), fullPage: true })
    }
    expect(errors).toEqual([])
  })
})
