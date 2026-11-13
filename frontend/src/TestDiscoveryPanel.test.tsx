// Phase 4 task A panel. `fetch` is stubbed; the canned answers have the shape
// the API returns (backend/tests/test_discovery.py pins it).
import { describe, expect, test } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from './App'
import { TestDiscoveryPanel } from './TestDiscoveryPanel'
import { deferred, stubApi } from './test/api'
import { demoReport, demoRoutes } from './test/fixtures'
import type { TestDiscovery } from './types'

const SCAN = 'scan-1'
const URL = `/api/scans/${SCAN}/tests/discovery`

const discovery = (change: Partial<TestDiscovery> = {}): TestDiscovery => ({
  scan_id: SCAN, ai_review_id: null, commit: 'c'.repeat(40), method: 'static-ast', executed: false,
  test_files_found: 2, test_files_read: 2, test_files_unread: 0, unparsed_test_files: [], tests_found: 5, candidate_count: 2,
  candidates: [
    { test_id: 'tests/test_auth.py::test_owner_can_read', file: 'tests/test_auth.py', name: 'test_owner_can_read', line: 4, changed_in_this_scan: false,
      reasons: [{ kind: 'imports_changed_module', changed_file: 'app/auth.py' }, { kind: 'mentions_changed_function', changed_file: 'app/auth.py', function: 'check' }],
      related_static_finding_ids: ['f1', 'f2'], related_ai_finding_ids: ['F1'] },
    { test_id: 'tests/test_auth.py::test_unrelated', file: 'tests/test_auth.py', name: 'test_unrelated', line: 9, changed_in_this_scan: true,
      reasons: [{ kind: 'imports_changed_module', changed_file: 'app/auth.py' }], related_static_finding_ids: [], related_ai_finding_ids: [] },
  ],
  coverage_gaps: [{ changed_file: 'app/pricing.py', reason: 'No discovered test file imports this module.', static_finding_ids: ['f3'], ai_finding_ids: [] }],
  incomplete: false, heuristics: ['Test files are parsed, never imported or run.'],
  disclaimer: 'Suggestions from static analysis.', ...change,
})
const open = (answer: unknown, status = 200) => { const api = stubApi({ [URL]: { status, body: answer } }); render(<TestDiscoveryPanel scanId={SCAN} />); return api }

describe('test discovery panel', () => {
  test('lists candidates with the reason they were selected, and never as run', async () => {
    open(discovery())
    const rows = (await screen.findAllByRole('row')).slice(1)
    expect(rows).toHaveLength(2)
    expect(within(rows[0]).getByText('test_owner_can_read')).toBeVisible()
    expect(within(rows[0]).getByText('tests/test_auth.py:4')).toBeVisible()
    expect(within(rows[0]).getByText('its file imports app/auth.py')).toBeVisible()
    expect(within(rows[0]).getByText('mentions changed function check() of app/auth.py')).toBeVisible()
    expect(within(rows[0]).getByText('2 static')).toBeVisible()
    expect(within(rows[0]).getByText('1 imported AI (unverified)')).toBeVisible()
    expect(within(rows[1]).getByText(/changed in this scan/)).toBeVisible()
    expect(within(rows[1]).getByText('None')).toBeVisible()
    expect(screen.getAllByText('Suggested · not run')).toHaveLength(2)
    expect(screen.getByText('NOT RUN')).toBeVisible()
    expect(screen.getByText(/Nothing was collected or executed/)).toBeVisible()
    expect(screen.getByText(/2 test files · 5 tests · 2 candidates/)).toBeVisible()
    expect(screen.getByText('cccccccccccc')).toBeVisible()
    for (const word of ['passed', 'failed', 'verified', 'Verified', 'Passed']) expect(screen.queryByText(word)).not.toBeInTheDocument()
  })

  test('shows coverage gaps with the findings left without a test, and the selection rules', async () => {
    open(discovery())
    expect(await screen.findByText('app/pricing.py')).toBeVisible()
    expect(screen.getByText(/No discovered test file imports this module\./)).toBeVisible()
    expect(screen.getByText(/1 finding here with no matched test\./)).toBeVisible()
    expect(screen.getByText('How tests are selected')).toBeInTheDocument()
    expect(screen.getByText('Test files are parsed, never imported or run.')).toBeInTheDocument()
  })

  test('no candidate is presented as a gap, not as safety', async () => {
    open(discovery({ candidates: [], candidate_count: 0, tests_found: 0, test_files_found: 0, coverage_gaps: [] }))
    expect(await screen.findByRole('heading', { name: 'No existing test was matched to this change' })).toBeVisible()
    expect(screen.getByText(/No pytest test was found at this commit\./)).toBeVisible()
    expect(screen.getByText(/not a sign of safety/)).toBeVisible()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  test('an incomplete discovery says what is missing', async () => {
    open(discovery({ incomplete: true, test_files_unread: 3, unparsed_test_files: ['tests/test_broken.py'], candidate_count: 400 }))
    const note = await screen.findByRole('note')
    expect(note).toHaveTextContent('Incomplete discovery.')
    expect(note).toHaveTextContent('3 test files were not read (limit reached).')
    expect(note).toHaveTextContent('Could not be parsed: tests/test_broken.py.')
    expect(note).toHaveTextContent('Only the first 2 candidates are listed.')
  })

  test('loading, then an error with the API’s reason and a working Retry', async () => {
    const pending = deferred<{ status: number; body: unknown }>()
    const api = stubApi({ [URL]: [() => pending.promise as never, { body: discovery() }] })
    render(<TestDiscoveryPanel scanId={SCAN} />)
    expect(screen.getByText('Looking for existing tests…')).toBeVisible()

    pending.resolve({ status: 409, body: { detail: 'This scan is not bound to a commit, so tests cannot be discovered for it. Scan again.' } })
    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText(/not bound to a commit/)).toBeVisible()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()

    await userEvent.click(within(alert).getByRole('button', { name: /Retry/ }))
    expect(await screen.findByRole('table')).toBeVisible()
    expect(api.count(URL)).toBe(2)
  })

  test('an answer for another scan is not shown', async () => {
    open(discovery({ scan_id: 'some-other-scan' }))
    await new Promise(resolve => setTimeout(resolve, 50))
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })
})

describe('Test intelligence page', () => {
  const report = demoReport()
  const url = `/api/scans/${report.id}/tests/discovery`

  test('discovery is requested only when the page is opened, and the page still says tests were not executed', async () => {
    const api = stubApi({ ...demoRoutes(), [url]: { body: discovery({ scan_id: report.id }) } })
    render(<App />)
    await screen.findByRole('heading', { name: 'Release overview' })
    expect(api.count(url)).toBe(0)

    await userEvent.click(within(screen.getByRole('navigation', { name: 'Primary navigation' })).getByRole('button', { name: /Test intelligence/ }))
    const panel = within(await screen.findByRole('region', { name: 'Existing tests for this change' }))
    expect(await panel.findByText('test_owner_can_read')).toBeVisible()
    expect(screen.getByText('NOT EXECUTED')).toBeVisible()  // the existing banner of the page
    expect(api.count(url)).toBe(1)
    expect(document.querySelector('.alert-error')).toBeNull()
  })

  test('a failing discovery does not break the page or raise the page banner', async () => {
    stubApi(demoRoutes())  // no discovery route: 404, like an older backend
    render(<App />)
    await screen.findByRole('heading', { name: 'Release overview' })
    await userEvent.click(within(screen.getByRole('navigation', { name: 'Primary navigation' })).getByRole('button', { name: /Test intelligence/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not discover tests')
    expect(screen.getByRole('heading', { name: 'Test intelligence' })).toBeVisible()
    expect(document.querySelector('.alert-error')).toBeNull()
  })
})
