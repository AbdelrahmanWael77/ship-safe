// Phase 6 panel: AI-written manual QC test cases and tester results. `fetch` is stubbed;
// the canned suites have the shape the API returns (backend/tests/test_qc_tests.py pins it).
import { describe, expect, test, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QcTestCasesPanel } from './QcTestCasesPanel'
import { stubApi } from './test/api'
import type { Routes } from './test/api'
import type { AIProvider, AIReview, QcStatus, QcTestSuite } from './types'

const SCAN = 'scan-1'
const URL = `/api/scans/${SCAN}/qc/test-suites`
const OPENAI: AIProvider = { provider: 'openai', label: 'OpenAI', configured: true, model: 'gpt-test', pricing_known: true }
const GEMINI: AIProvider = { provider: 'gemini', label: 'Gemini', configured: true, model: 'gemini-test', pricing_known: false }
const review = (findings = 2) => ({
  id: 'r1', imported_at: '2026-11-13T10:00:00+00:00', source: 'openai_api_generated_unverified',
  generator: { provider: 'openai', model: 'gpt-test' }, verification_status: 'not_independently_verified', tests_executed: false,
  findings: Array.from({ length: findings }, (_, index) => ({ id: `F${index + 1}`, title: `Finding ${index + 1}`, severity: 'high', file: 'lib/a.dart' })),
  test_ideas: [], recommendation: 'needs_review',
}) as unknown as AIReview

const suite = (status: QcStatus = 'not_run', results: QcTestSuite['cases'][number]['results'] = []): QcTestSuite => ({
  id: 's1', scan_id: SCAN, review_id: 'r1', created_at: '2026-11-13T11:00:00+00:00', review_origin: 'OpenAI · gpt-test',
  cases: [{
    id: 'TC1', title: 'Double tap on Save sends one request', priority: 'high', area: 'Profile', finding_id: 'F1', file: 'lib/a.dart',
    preconditions: ['Signed in'], test_data: ['Any name'], steps: ['Open profile', 'Tap Save twice quickly'],
    expected: 'Only one request is sent and one toast shows.', bug_title_if_fails: 'Save sends duplicate requests on double tap',
    status, result: results[results.length - 1] ?? null, results,
  }],
  counts: { passed: status === 'passed' ? 1 : 0, failed: status === 'failed' ? 1 : 0, blocked: 0, not_run: status === 'not_run' ? 1 : 0 },
  total: 1, limitations: ['Written by an AI model from unverified findings. ShipSafe executed nothing.'], executed_by_shipsafe: false,
  generator: { provider: 'openai', model: 'gpt-test' },
})
const failed = () => suite('failed', [{ status: 'failed', tester: 'Mona', note: 'Two toasts', recorded_at: '2026-11-13T12:00:00+00:00' }])

const open = (routes: Routes, props: Partial<Parameters<typeof QcTestCasesPanel>[0]> = {}) => {
  const api = stubApi(routes)
  const onOpenReview = vi.fn()
  render(<QcTestCasesPanel scanId={SCAN} review={review()} providers={[OPENAI]} shareAckRequired={false} onOpenReview={onOpenReview} {...props} />)
  return { api, onOpenReview }
}
const posted = () => vi.mocked(fetch).mock.calls.filter(call => call[1]?.method === 'POST').map(call => ({ url: String(call[0]), body: JSON.parse(String(call[1]?.body)) }))

describe('QC test cases', () => {
  test('without an AI review it points to the review page and sends nothing', async () => {
    const { onOpenReview } = open({ [URL]: { body: [] } }, { review: undefined })
    await userEvent.click(await screen.findByRole('button', { name: /Run an AI review/ }))
    expect(onOpenReview).toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: /Write test cases/ })).toBeNull()
    expect(posted()).toEqual([])
  })

  test('writing test cases sends the review id and shows the cases as not run', async () => {
    open({ [URL]: [{ body: [] }, { body: [suite()] }], [`POST ${URL}`]: { status: 201, body: suite() } })
    await userEvent.click(await screen.findByRole('button', { name: 'Write test cases with OpenAI' }))
    expect(posted()[0]).toEqual({ url: expect.stringContaining(URL), body: { provider: 'openai', review_id: 'r1', acknowledge_source_sharing: false } })
    expect(await screen.findByText(/1 test case written by OpenAI from 2 findings/)).toBeVisible()
    const item = within(screen.getByRole('article', { name: 'Test case TC1' }))
    expect(item.getByText('Double tap on Save sends one request')).toBeInTheDocument()
    expect(item.getByText('Not run')).toBeInTheDocument()
    expect(screen.getByText('MANUAL · SHIPSAFE RUNS NOTHING')).toBeVisible()
    expect(screen.getByRole('link', { name: /CSV/ })).toHaveAttribute('href', `${URL}/s1/export?format=csv`)
    expect(screen.getByRole('link', { name: /Markdown/ })).toHaveAttribute('href', `${URL}/s1/export?format=markdown`)
  })

  test('non-demo code needs the sharing confirmation before anything is sent', async () => {
    open({ [URL]: { body: [] }, [`POST ${URL}`]: { status: 201, body: suite() } }, { shareAckRequired: true, providers: [OPENAI, GEMINI] })
    const button = await screen.findByRole('button', { name: 'Write test cases with OpenAI' })
    expect(button).toBeDisabled()
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Model for test cases' }), 'gemini')
    await userEvent.click(screen.getByRole('checkbox'))
    await userEvent.click(screen.getByRole('button', { name: 'Write test cases with Gemini' }))
    expect(posted()[0].body).toEqual({ provider: 'gemini', review_id: 'r1', acknowledge_source_sharing: true })
  })

  test('recording a result needs a name and sends status, tester and note', async () => {
    open({ [URL]: { body: [suite()] }, [`POST ${URL}/s1/results`]: { status: 201, body: failed() } })
    const item = within(await screen.findByRole('article', { name: 'Test case TC1' }))
    expect(item.getByRole('button', { name: /Failed/ })).toBeDisabled()
    await userEvent.type(screen.getByRole('textbox', { name: 'Tester name' }), 'Mona')
    await userEvent.type(item.getByRole('textbox', { name: 'Note for TC1' }), 'Two toasts')
    await userEvent.click(item.getByRole('button', { name: /Failed/ }))
    expect(posted()[0]).toEqual({ url: expect.stringContaining(`${URL}/s1/results`), body: { case_id: 'TC1', status: 'failed', tester: 'Mona', note: 'Two toasts' } })
    expect(await screen.findByText('1 failed')).toBeVisible()
    expect(item.getByText(/Mona/)).toBeInTheDocument()
  })

  test('a refused generation is reported and nothing is shown as written', async () => {
    open({ [URL]: { body: [] }, [`POST ${URL}`]: { status: 502, body: { detail: 'The model returned no usable test case.', code: 'openai_no_test_cases' } } })
    await userEvent.click(await screen.findByRole('button', { name: 'Write test cases with OpenAI' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/Test cases not written: The model returned no usable test case/)
    expect(screen.queryByRole('article')).toBeNull()
  })

  test('a review with no findings has nothing to write', async () => {
    open({ [URL]: { body: [] } }, { review: review(0) })
    expect(await screen.findByText(/proposed no findings/)).toBeVisible()
    expect(screen.queryByRole('button', { name: /Write test cases/ })).toBeNull()
  })
})
