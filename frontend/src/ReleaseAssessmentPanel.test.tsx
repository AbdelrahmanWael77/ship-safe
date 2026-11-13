// Phase 5 release assessment page. `fetch` is stubbed; the canned assessment
// has the shape the API returns (backend/tests/test_assessment.py pins it).
import { describe, expect, test } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from './App'
import { ReleaseAssessmentPanel } from './ReleaseAssessmentPanel'
import { stubApi } from './test/api'
import { demoReport, demoRoutes } from './test/fixtures'
import type { ReleaseAssessment } from './types'

const SCAN = 'scan-1'
const URL = `/api/scans/${SCAN}/assessment`
const STATEMENT = 'This assessment does not say the change is safe. It lists what was found, what was only suggested, what was actually executed, and what is unknown. A person decides.'

const assessment = (change: Partial<ReleaseAssessment> = {}): ReleaseAssessment => ({
  scan_id: SCAN, generated_at: '2026-11-13T12:00:00+00:00', state: 'tests_incomplete', state_label: 'Tests incomplete',
  states: ['tests_incomplete', 'review_required'], statement: STATEMENT,
  identity: { repo_name: 'Ledger', provider: 'bitbucket-cloud', repository_id: 'acme/ledger', pull_request_id: '7', base_ref: 'main',
    head_ref: 'feature/change-7', base_commit: 'a'.repeat(40), head_commit: 'b'.repeat(40), comparison: 'merge-base',
    scanned_at: '2026-11-13T10:00:00+00:00', stale: false, stale_at: null },
  static: { label: 'SUSPECTED (static heuristics, not verified)', finding_count: 1, by_severity: { critical: 0, high: 1, medium: 0, low: 0 },
    risk_score: 45, recommendation: 'Critical review required', files_changed: 1,
    findings: [{ id: 'f1', severity: 'high', category: 'authorization', title: 'Ownership check removed', file: 'app/auth.py', line: 12 }] },
  ai_reviews: { label: 'UNVERIFIED (imported JSON, provenance not verified)', count: 1, latest: { id: 'r1', imported_at: '2026-11-13T11:00:00+00:00',
    schema_version: 'shipsafe.ai-review.v2', recommendation: 'manual_review', finding_count: 1,
    findings: [{ id: 'F1', severity: 'medium', category: 'validation', title: 'Imported AI finding', file: 'app/auth.py', line: null, confidence: 'low' }] } },
  tests: { label: 'EXECUTED RESULTS ONLY count as test evidence', repository_test_status: 'not_run',
    proposals: { count: 2, by_status: { pending: 1, approved: 1, rejected: 0 }, items: [
      { id: 'p1', target_path: 'tests/test_auth_regression.py', status: 'approved', finding_ref: 'f1', origin: 'human',
        decisions: [{ decision: 'approved', decided_by: 'Nour Waled', decided_at: '2026-11-13T11:30:00+00:00', note: null }] },
      { id: 'p2', target_path: 'tests/test_other.py', status: 'pending', finding_ref: null, origin: 'human', decisions: [] }] },
    runs: { requested: 1, blocked: 1, executed: 0, confirmed_regressions: 0, items: [{ id: 'run1', status: 'blocked', executed: false }] } },
  unknowns: ['No test was executed by ShipSafe for this scan. There is no pass or fail evidence, no baseline comparison and no confirmed regression.',
    'Static findings are heuristic suspicions. None has been confirmed or dismissed by ShipSafe.'],
  ...change,
})
const open = (body: unknown, status = 200) => { const api = stubApi({ [URL]: { status, body } }); render(<ReleaseAssessmentPanel scanId={SCAN} />); return api }

describe('release assessment', () => {
  test('shows the state, the statement that it is not an approval, and what was assessed with full commits', async () => {
    open(assessment())
    expect(await screen.findByText('Tests incomplete')).toBeVisible()
    expect(screen.getByText('Review required')).toBeVisible()
    expect(screen.getByText(STATEMENT)).toBeVisible()
    expect(screen.getByText('acme/ledger')).toBeVisible()
    expect(screen.getByText('a'.repeat(40))).toBeVisible()
    expect(screen.getByText('b'.repeat(40))).toBeVisible()
    expect(screen.queryByRole('note')).not.toBeInTheDocument()  // not stale
  })

  test('keeps the three kinds of evidence apart and never presents a blocked run as a result', async () => {
    open(assessment())
    const staticPanel = within(await screen.findByRole('region', { name: 'Static findings' }))
    expect(staticPanel.getByText('SUSPECTED (static heuristics, not verified)')).toBeVisible()
    expect(staticPanel.getByText('Ownership check removed')).toBeVisible()
    expect(staticPanel.queryByText('Imported AI finding')).not.toBeInTheDocument()

    const ai = within(screen.getByRole('region', { name: 'Imported AI reviews' }))
    expect(ai.getByText('UNVERIFIED (imported JSON, provenance not verified)')).toBeVisible()
    expect(ai.getByText('Imported AI finding')).toBeVisible()
    expect(ai.queryByText('Ownership check removed')).not.toBeInTheDocument()

    const tests = within(screen.getByRole('region', { name: 'Test evidence' }))
    expect(tests.getByText('0 executed')).toBeVisible()
    expect(tests.getByText('1 of 1')).toBeVisible()                         // blocked of requested
    expect(tests.getByText('1 approved · 0 rejected · 1 pending')).toBeVisible()
    expect(tests.getByText(/approved by Nour Waled/)).toBeVisible()
    expect(tests.getByText('No test was executed. Nothing here is test evidence.')).toBeVisible()
    for (const word of ['passed', 'Passed', 'verified safe', 'safe to release']) expect(screen.queryByText(new RegExp(word))).not.toBeInTheDocument()
  })

  test('lists what is not known and offers both exports tied to the scan', async () => {
    open(assessment())
    const unknowns = within(await screen.findByRole('region', { name: 'What is not known' }))
    expect(unknowns.getAllByRole('listitem')).toHaveLength(2)
    expect(unknowns.getByText(/No test was executed by ShipSafe/)).toBeVisible()
    expect(screen.getByRole('link', { name: /Export JSON/ })).toHaveAttribute('href', URL)
    expect(screen.getByRole('link', { name: /Export report/ })).toHaveAttribute('href', `${URL}/report`)
  })

  test.each([
    ['stale', 'Stale'], ['confirmed_regression', 'Confirmed regression'], ['assessment_unavailable', 'Assessment unavailable'],
    ['review_required', 'Review required'],
  ] as const)('state %s is shown as "%s"', async (state, label) => {
    open(assessment({ state, state_label: label, states: [state] }))
    expect(await screen.findByText(label)).toBeVisible()
  })

  test('a stale assessment says the evidence describes an older change', async () => {
    const stale = assessment({ state: 'stale', state_label: 'Stale', states: ['stale', 'tests_incomplete', 'review_required'] })
    stale.identity = { ...stale.identity, stale: true, stale_at: '2026-11-13T11:45:00+00:00' }
    open(stale)
    expect(await screen.findByRole('note')).toHaveTextContent(/the pull request has new commits\. Everything on this page describes an older change\./)
  })

  test('no findings and no review are stated without implying safety', async () => {
    const empty = assessment()
    empty.static = { ...empty.static, finding_count: 0, findings: [] }
    empty.ai_reviews = { ...empty.ai_reviews, count: 0, latest: null }
    open(empty)
    expect(await screen.findByText('No known pattern was flagged. That is not evidence of safety.')).toBeVisible()
    expect(screen.getByText('None imported.')).toBeVisible()
    expect(screen.getByText('Tests incomplete')).toBeVisible()
  })

  test('when the assessment cannot be read the page says "unavailable", not "fine", and Retry works', async () => {
    const api = stubApi({ [URL]: [{ status: 500, body: { detail: 'boom' } }, { body: assessment() }] })
    render(<ReleaseAssessmentPanel scanId={SCAN} />)
    const alert = await screen.findByRole('alert')
    expect(within(alert).getByRole('heading', { name: 'Assessment unavailable' })).toBeVisible()
    expect(screen.queryByRole('region', { name: 'Static findings' })).not.toBeInTheDocument()
    await userEvent.click(within(alert).getByRole('button', { name: /Retry/ }))
    expect(await screen.findByRole('region', { name: 'Static findings' })).toBeVisible()
    expect(api.count(URL)).toBe(2)
  })

  test('an assessment of another scan is not shown', async () => {
    open(assessment({ scan_id: 'another-scan' }))
    await new Promise(resolve => setTimeout(resolve, 50))
    expect(screen.queryByRole('region', { name: 'Static findings' })).not.toBeInTheDocument()
  })
})

describe('dashboard', () => {
  test('Release assessment is a page of the workspace and loads only when opened', async () => {
    const report = demoReport()
    const url = `/api/scans/${report.id}/assessment`
    const api = stubApi({ ...demoRoutes(), [url]: { body: assessment({ scan_id: report.id }) } })
    render(<App />)
    await screen.findByRole('heading', { name: 'Release overview' })
    expect(api.count(url)).toBe(0)
    await userEvent.click(within(screen.getByRole('navigation', { name: 'Primary navigation' })).getByRole('button', { name: /Release assessment/ }))
    expect(await screen.findByRole('region', { name: 'Release assessment' })).toBeVisible()
    expect(await screen.findByText('Tests incomplete')).toBeVisible()
    expect(document.querySelector('.topbar-left strong')).toHaveTextContent('Release assessment')
    expect(api.count(url)).toBe(1)
    expect(document.querySelector('.alert-error')).toBeNull()
  })
})
