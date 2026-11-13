// "Scan this pull request" followed by an AI model review (OpenAI or Gemini) on the PR analysis page.
import { beforeEach, describe, expect, test, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { stubApi } from '../test/api'
import type { Routes } from '../test/api'
import { pullRequestDetail, pullRequestScanReport, statusConfigured } from '../test/fixtures'
import type { AIProvider, AIReview } from '../types'
import { getBitbucketStatus } from './client'
import type { BitbucketSelection } from './pages'
import { PrAnalysisPage } from './PrAnalysisPage'
import { useLoad } from './useLoad'

const DETAIL = '/api/bitbucket/repositories/ledger/pull-requests/7'
const SELECTED: BitbucketSelection = { slug: 'ledger', state: 'open', pullRequestId: '7' }
const report = pullRequestScanReport()
const REVIEW = `POST /api/scans/${report.id}/ai/model-reviews`
const REPO_KEY = `shipsafe.ai-review:${pullRequestDetail().repository.id}`
const onOpenReport = vi.fn()

const OPENAI: AIProvider = { provider: 'openai', label: 'OpenAI', configured: true, model: 'gpt-6-luna', pricing_known: true }
const GEMINI: AIProvider = { provider: 'gemini', label: 'Google Gemini', configured: true, model: 'gemini-test', pricing_known: false }

const review = (provider: 'openai' | 'gemini' = 'openai'): AIReview => ({
  id: 'r1', imported_at: '2026-11-13T12:00:00+00:00',
  source: provider === 'openai' ? 'openai_api_generated_unverified' : 'gemini_api_generated_unverified',
  generator: { provider, model: provider === 'openai' ? 'gpt-6-luna' : 'gemini-test',
    usage: { input_tokens: 3400, output_tokens: 2600, reasoning_tokens: 700 }, duration_ms: 18200,
    ...(provider === 'openai' ? { estimated_cost_usd: 0.00164, prices_as_of: '2026-11-13' } : {}) },
  verification_status: 'not_independently_verified', tests_executed: false, schema_version: 'shipsafe.ai-review.v2',
  scan_id: report.id, context_digest: '0'.repeat(64), summary: 'The payment page accepts bad certificates.', recommendation: 'block_release',
  findings: [{ id: 'G1', status: 'suspected', title: 'TLS errors accepted', severity: 'critical', category: 'Security', file: report.files[0].path, line: 3,
    evidence: 'proceed()', rationale: 'Certificate errors no longer stop the page.', recommendation: 'Cancel.', confidence: 'high',
    related_static_finding_ids: [], suggested_validation: 'Use a self-signed certificate.' }],
  test_ideas: [{ title: 'Bad certificate is refused', scenario: 'Serve a self-signed certificate.', expected_behavior: 'The load is cancelled.', file: null }],
  limitations: ['Static review.'], missing_context: [],
})

function Page({ providers }: { providers: AIProvider[] | null }) {
  return <PrAnalysisPage status={useLoad(getBitbucketStatus, 'bitbucket-status')} selection={SELECTED} navigate={vi.fn()} onScanned={vi.fn()} onOpenReport={onOpenReport} providers={providers} />
}
const open = (routes: Routes, providers: AIProvider[] | null = [OPENAI]) => {
  const api = stubApi({ '/api/bitbucket/status': { body: statusConfigured() }, [DETAIL]: { body: pullRequestDetail() }, [`POST ${DETAIL}/scans`]: { status: 201, body: report }, ...routes })
  render(<Page providers={providers} />)
  return api
}
const toggle = () => screen.findByRole('checkbox', { name: /Also review with AI/ })
const scanButton = () => screen.getByRole('button', { name: /Scan this pull request/ })
const reviewBodies = () => vi.mocked(fetch).mock.calls.filter(call => String(call[0]).endsWith('/ai/model-reviews')).map(call => JSON.parse(String(call[1]?.body)))

beforeEach(() => { window.localStorage.clear(); onOpenReport.mockClear() })

describe('AI model review from the PR analysis page', () => {
  test('without the confirmation, scanning sends nothing to an AI model', async () => {
    const api = open({ [REVIEW]: { status: 201, body: review() } })
    expect(await toggle()).not.toBeChecked()
    await userEvent.click(scanButton())
    expect(await screen.findByRole('region', { name: 'Scan report' })).toBeVisible()
    expect(api.count(REVIEW)).toBe(0)
    expect(within(screen.getByRole('region', { name: 'AI review' })).getByText(/Tick “Also review with AI”/)).toBeVisible()
  })

  test('with the confirmation, one click scans, reviews with OpenAI and shows risks, test ideas, tokens and cost', async () => {
    const api = open({ [REVIEW]: { status: 201, body: review() } })
    await userEvent.click(await toggle())
    expect(scanButton()).toHaveTextContent('Scan this pull request + AI review')
    await userEvent.click(scanButton())

    const ai = within(await screen.findByRole('region', { name: 'AI review' }))
    expect(await ai.findByText('G1 · TLS errors accepted')).toBeVisible()
    expect(ai.getByText(/OpenAI · gpt-6-luna/)).toBeVisible()
    expect(ai.getByText('6,000 tokens (3,400 in · 2,600 out, 700 reasoning) · ≈ $0.0016 · 18.2 s')).toBeVisible()
    expect(ai.getByText('Bad certificate is refused')).toBeVisible()
    expect(api.count(REVIEW)).toBe(1)
    expect(reviewBodies()).toEqual([{ provider: 'openai', acknowledge_source_sharing: true }])

    await userEvent.click(ai.getByRole('button', { name: /Risk findings/ }))
    expect(onOpenReport).toHaveBeenCalledWith(report.id, 'findings')
    await userEvent.click(ai.getByRole('button', { name: /Test intelligence/ }))
    expect(onOpenReport).toHaveBeenCalledWith(report.id, 'tests')
  })

  test('the confirmed provider is remembered for the repository', async () => {
    open({})
    await userEvent.click(await toggle())
    expect(window.localStorage.getItem(REPO_KEY)).toBe('openai')
    await userEvent.click(await toggle())
    expect(window.localStorage.getItem(REPO_KEY)).toBeNull()
  })

  test('with two providers the person picks one; switching company clears the confirmation', async () => {
    open({ [REVIEW]: { status: 201, body: review('gemini') } }, [GEMINI, OPENAI])
    const picker = await screen.findByRole('combobox', { name: 'AI model' })
    expect(picker).toHaveValue('openai')  // OpenAI first when both are configured
    await userEvent.click(await toggle())
    await userEvent.selectOptions(picker, 'gemini')
    expect(await toggle()).not.toBeChecked()
    expect(window.localStorage.getItem(REPO_KEY)).toBeNull()

    await userEvent.click(await toggle())
    await userEvent.click(scanButton())
    expect(await screen.findByText(/Google Gemini|Gemini · gemini-test/, { selector: '.bb-ai p' })).toBeVisible()
    expect(reviewBodies()).toEqual([{ provider: 'gemini', acknowledge_source_sharing: true }])
  })

  test('a failure is shown with Try again; the scan report stays', async () => {
    const api = open({ [REVIEW]: [{ status: 429, body: { detail: 'OpenAI rate limit.', code: 'openai_rate_limited' } }, { status: 201, body: review() }] })
    await userEvent.click(await toggle())
    await userEvent.click(scanButton())
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('OpenAI review failed: OpenAI rate limit.')
    expect(screen.getByRole('region', { name: 'Scan report' })).toBeVisible()
    await userEvent.click(within(alert).getByRole('button', { name: /Try again/ }))
    expect(await screen.findByText('G1 · TLS errors accepted')).toBeVisible()
    expect(api.count(REVIEW)).toBe(2)
  })

  test('without any AI model on the server there is no toggle and the scan works as before', async () => {
    const api = open({}, [])
    await screen.findByRole('button', { name: /Scan this pull request/ })
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    await userEvent.click(scanButton())
    expect(await within(await screen.findByRole('region', { name: 'AI review' })).findByText(/No AI model is configured/)).toBeVisible()
    expect(api.calls.some(call => call.includes('model-reviews'))).toBe(false)
  })
})
