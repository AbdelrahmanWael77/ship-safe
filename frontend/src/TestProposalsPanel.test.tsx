// Phase 4 task B panel. `fetch` is stubbed; the canned proposals have the
// shape the API returns (backend/tests/test_proposals.py pins it).
import { describe, expect, test, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from './App'
import { TestProposalsPanel } from './TestProposalsPanel'
import { stubApi } from './test/api'
import type { Routes } from './test/api'
import { demoReport, demoRoutes } from './test/fixtures'
import type { TestProposal } from './types'

const SCAN = 'scan-1'
const URL = `/api/scans/${SCAN}/tests/proposals`
const CONTENT = 'def test_other_user_is_refused():\n    assert get_invoice("mallory") is None\n<img src=x onerror="window.__xss = 1">'

const proposal = (change: Partial<TestProposal> = {}): TestProposal => ({
  id: 'p1', scan_id: SCAN, created_at: '2026-11-13T10:00:00+00:00', target_path: 'tests/test_auth_regression.py',
  content: CONTENT, content_digest: 'd'.repeat(64), origin: 'human', finding_ref: 'f1', rationale: 'The ownership check was removed.',
  base_commit: 'a'.repeat(40), head_commit: 'b'.repeat(40), decisions: [], status: 'pending', stale: false,
  eligible_to_run: false, applied: false, executed: false,
  identity_note: 'ShipSafe has no authentication: the name recorded with a decision is typed by the person and is not verified.',
  ...change,
})
const approved = () => proposal({
  status: 'approved', eligible_to_run: true,
  decisions: [{ id: 'd1', decision: 'approved', decided_at: '2026-11-13T11:00:00+00:00', decided_by: 'Nour Waled', note: 'Looks right.' }],
})
const open = (routes: Routes) => { const api = stubApi(routes); render(<TestProposalsPanel scanId={SCAN} />); return api }
const card = async (path = 'tests/test_auth_regression.py') => within(await screen.findByRole('article', { name: `Proposal ${path}` }))
const posted = () => vi.mocked(fetch).mock.calls.filter(call => call[1]?.method === 'POST').map(call => ({ url: String(call[0]), body: JSON.parse(String(call[1]?.body)) }))

describe('proposed tests', () => {
  test('a proposal is shown in full as inert text, bound to its commits, pending, and not runnable', async () => {
    open({ [URL]: { body: [proposal()] } })
    const item = await card()
    expect(item.getByText('Pending decision')).toBeVisible()
    expect(item.getByText('aaaaaaaaaaaa')).toBeVisible()
    expect(item.getByText('bbbbbbbbbbbb')).toBeVisible()
    expect(item.getByText('f1')).toBeVisible()
    expect(item.getByText('The ownership check was removed.')).toBeVisible()
    const content = within(item.getByRole('region', { name: 'Proposed content of tests/test_auth_regression.py' }))
    expect(content.getByText('+def test_other_user_is_refused():')).toBeVisible()
    expect(content.getByText(/onerror=/)).toBeVisible()            // shown as text
    expect(document.querySelector('.proposal img')).toBeNull()      // not turned into an element
    expect((window as unknown as { __xss?: number }).__xss).toBeUndefined()

    expect(item.getByRole('button', { name: /Run.*BLOCKED/ })).toBeDisabled()
    expect(item.getByText(/Run is blocked: no verified isolated runner is available\. Only an approved proposal could run\./)).toBeVisible()
    expect(item.getByText('No decision yet.')).toBeVisible()
    expect(item.getByText(/is not verified/)).toBeVisible()
    expect(screen.getByText('NOT APPLIED · NOT RUN')).toBeVisible()
  })

  test('approving needs a name, records the decision, and still does not enable Run', async () => {
    const api = open({ [URL]: [{ body: [proposal()] }, { body: [approved()] }], [`POST ${URL}/p1/decisions`]: { status: 201, body: approved() } })
    const item = await card()
    const approve = item.getByRole('button', { name: /Approve/ })
    expect(approve).toBeDisabled()
    expect(item.getByRole('button', { name: /Reject/ })).toBeDisabled()

    await userEvent.type(item.getByRole('textbox', { name: /Your name/ }), 'Nour Waled')
    await userEvent.type(item.getByRole('textbox', { name: /Note/ }), 'Looks right.')
    await userEvent.click(approve)

    expect(await screen.findByText('Approved', { selector: '.pill' })).toBeVisible()
    expect(posted()).toEqual([{ url: `${URL}/p1/decisions`, body: { decision: 'approved', decided_by: 'Nour Waled', note: 'Looks right.' } }])
    const after = await card()
    expect(after.getByText(/by Nour Waled/)).toBeVisible()
    expect(after.getByText(/approved for these commits and would be allowed to run once one is/)).toBeVisible()
    expect(api.count(URL)).toBe(2)
  })

  const blockedRun = { id: 'r1', proposal_id: 'p1', scan_id: SCAN, requested_at: '2026-11-13T12:00:00+00:00', requested_by: 'Nour Waled', status: 'blocked',
    reason: 'No verified isolated test runner is configured. ShipSafe never runs repository tests on its own host, so nothing was executed.',
    runner: 'none', base_commit: 'a'.repeat(40), head_commit: 'b'.repeat(40), started_at: null, finished_at: null, exit_code: null, output: null, executed: false }

  test('requesting a run of an approved proposal reports BLOCKED with the runner’s reason and lists the blocked request', async () => {
    const RUNS = `${URL}/p1/runs`
    open({ [URL]: { body: [approved()] }, [RUNS]: [{ body: [] }, { body: [blockedRun] }],
      [`POST ${RUNS}`]: { status: 503, body: { detail: blockedRun.reason, code: 'execution_unavailable', run: blockedRun } } })
    const item = await card()
    const run = item.getByRole('button', { name: /Run.*BLOCKED/ })
    expect(run).toBeDisabled()                                          // a name is required first
    await userEvent.type(item.getByRole('textbox', { name: /Your name/ }), 'Nour Waled')
    await userEvent.click(run)

    expect(await item.findByRole('status')).toHaveTextContent('BLOCKED. No verified isolated test runner is configured.')
    expect(posted()).toEqual([{ url: RUNS, body: { requested_by: 'Nour Waled' } }])
    const entry = await item.findByText('BLOCKED · not executed')
    expect(entry.closest('li')).toHaveTextContent('requested by Nour Waled')
    expect(entry.closest('li')).toHaveTextContent('runner: none')
    for (const word of ['passed', 'failed', 'Passed', 'Failed', 'exit code']) expect(item.queryByText(new RegExp(word))).not.toBeInTheDocument()
  })

  test('a pending or rejected proposal cannot request a run even with a name', async () => {
    open({ [URL]: { body: [proposal(), proposal({ id: 'p2', target_path: 'tests/test_two.py', status: 'rejected',
      decisions: [{ id: 'd9', decision: 'rejected', decided_at: '2026-11-13T11:00:00+00:00', decided_by: 'Nour', note: null }] })] } })
    for (const path of ['tests/test_auth_regression.py', 'tests/test_two.py']) {
      const item = await card(path)
      await userEvent.type(item.getByRole('textbox', { name: /Your name/ }), 'Nour Waled')
      expect(item.getByRole('button', { name: /Run.*BLOCKED/ })).toBeDisabled()
    }
    expect(posted()).toEqual([])
  })

  test('rejecting records a rejection; a refused decision shows the API’s reason', async () => {
    open({ [URL]: { body: [proposal()] }, [`POST ${URL}/p1/decisions`]: { status: 409, body: { detail: 'This proposal is stale: the pull request has new commits since its scan. It can be rejected, not approved.' } } })
    const item = await card()
    await userEvent.type(item.getByRole('textbox', { name: /Your name/ }), 'Nour')
    await userEvent.click(item.getByRole('button', { name: /Reject/ }))
    expect(posted()[0].body).toEqual({ decision: 'rejected', decided_by: 'Nour' })
    expect(await item.findByRole('alert')).toHaveTextContent('Decision not recorded: This proposal is stale')
    expect(item.getByText('Pending decision')).toBeVisible()
  })

  test('a stale proposal says so, cannot be approved, and would not run even if approved', async () => {
    open({ [URL]: { body: [{ ...approved(), stale: true, eligible_to_run: false }] } })
    const item = await card()
    expect(item.getByText('Stale · pull request has new commits')).toBeVisible()
    expect(item.getByText(/This proposal is stale and could not run even then\./)).toBeVisible()
    await userEvent.type(item.getByRole('textbox', { name: /Your name/ }), 'Nour')
    expect(item.getByRole('button', { name: /Approve/ })).toBeDisabled()
    expect(item.getByRole('button', { name: /Reject/ })).toBeEnabled()
  })

  test('decision history is listed oldest first', async () => {
    open({ [URL]: { body: [proposal({
      status: 'approved', eligible_to_run: true, decisions: [
        { id: 'd1', decision: 'rejected', decided_at: '2026-11-13T10:30:00+00:00', decided_by: 'Reviewer One', note: null },
        { id: 'd2', decision: 'approved', decided_at: '2026-11-13T11:30:00+00:00', decided_by: 'Reviewer Two', note: 'Fixed.' },
      ] })] } })
    const entries = (await card()).getAllByRole('listitem')
    expect(entries[0]).toHaveTextContent(/^Rejected by Reviewer One/)
    expect(entries[1]).toHaveTextContent(/^Approved by Reviewer Two .* Fixed\.$/)
  })

  test('adding a proposal sends exactly what was typed and reports the result next to the form', async () => {
    const api = open({ [URL]: [{ body: [] }, { body: [proposal()] }], [`POST ${URL}`]: { status: 201, body: proposal() } })
    expect(await screen.findByRole('heading', { name: 'No test has been proposed for this scan' })).toBeVisible()
    await userEvent.click(screen.getByText('Propose a new test file'))
    const path = screen.getByRole('textbox', { name: 'Target path' })
    await userEvent.clear(path)
    await userEvent.type(path, 'tests/test_auth_regression.py')
    await userEvent.type(screen.getByRole('textbox', { name: 'Finding id' }), 'f1')
    await userEvent.click(screen.getByRole('textbox', { name: 'Test source' }))
    await userEvent.paste('def test_a():\n    assert True\n')
    await userEvent.click(screen.getByRole('button', { name: 'Store proposal' }))

    expect(await screen.findByRole('status')).toHaveTextContent('It is pending a decision; nothing was applied or run.')
    expect(posted()).toEqual([{ url: URL, body: { target_path: 'tests/test_auth_regression.py', content: 'def test_a():\n    assert True\n', origin: 'human', finding_ref: 'f1' } }])
    expect(await card()).toBeTruthy()
    expect(api.count(URL)).toBe(2)
  })

  test('a refused proposal shows the API’s reason and keeps what was typed', async () => {
    open({ [URL]: { body: [] }, [`POST ${URL}`]: { status: 422, body: { detail: "Target path must be inside a directory named 'tests' or 'test'." } } })
    await screen.findByRole('heading', { name: 'No test has been proposed for this scan' })
    await userEvent.click(screen.getByText('Propose a new test file'))
    const path = screen.getByRole('textbox', { name: 'Target path' })
    await userEvent.clear(path)
    await userEvent.type(path, 'app/test_x.py')
    await userEvent.click(screen.getByRole('textbox', { name: 'Test source' }))
    await userEvent.paste('def test_a():\n    pass\n')
    await userEvent.click(screen.getByRole('button', { name: 'Store proposal' }))
    expect(await screen.findByRole('alert')).toHaveTextContent("Not stored: Target path must be inside a directory named 'tests' or 'test'.")
    expect(screen.getByRole('textbox', { name: 'Test source' })).toHaveValue('def test_a():\n    pass\n')
  })

  test('loading failure offers Retry; a proposal of another scan is never shown', async () => {
    const api = open({ [URL]: [{ status: 500, body: { detail: 'boom' } }, { body: [proposal({ scan_id: 'another-scan' })] }] })
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Could not load the proposals')
    await userEvent.click(within(alert).getByRole('button', { name: /Retry/ }))
    expect(await screen.findByRole('heading', { name: 'No test has been proposed for this scan' })).toBeVisible()
    expect(screen.queryByRole('article')).not.toBeInTheDocument()
    expect(api.count(URL)).toBe(2)
  })
})

describe('proposed tests of a repository other than the demo', () => {
  test('Run is not offered: the text says runs are only for the demo repository, and no run is requested', async () => {
    const api = stubApi({ [URL]: { body: [approved()] }, [`${URL}/${approved().id}/runs`]: { body: [] } })
    render(<TestProposalsPanel scanId={SCAN} runRefused />)
    const item = within(await screen.findByRole('article', { name: `Proposal ${approved().target_path}` }))
    await userEvent.type(item.getByRole('textbox', { name: /Your name/ }), 'QC Test')
    expect(item.getByRole('button', { name: /Run/ })).toBeDisabled()
    expect(item.getByText(/Run is not available for this repository/)).toBeVisible()
    expect(item.queryByText(/would be allowed to run once one is/)).not.toBeInTheDocument()
    expect(api.calls.some(call => call.startsWith('POST'))).toBe(false)
  })
})

describe('Test intelligence page', () => {
  test('shows the proposals of the scan on screen and never a working Run control', async () => {
    const report = demoReport()
    const url = `/api/scans/${report.id}/tests/proposals`
    const api = stubApi({ ...demoRoutes(), [url]: { body: [{ ...approved(), scan_id: report.id }] } })
    render(<App />)
    await screen.findByRole('heading', { name: 'Release overview' })
    expect(api.count(url)).toBe(0)
    await userEvent.click(within(screen.getByRole('navigation', { name: 'Primary navigation' })).getByRole('button', { name: /Test intelligence/ }))
    const panel = within(await screen.findByRole('region', { name: 'Proposed regression tests' }))
    expect(await panel.findByText('Approved', { selector: '.pill' })).toBeVisible()
    for (const button of panel.getAllByRole('button', { name: /Run/ })) expect(button).toBeDisabled()
    expect(screen.getByText('NOT EXECUTED')).toBeVisible()
    expect(document.querySelector('.alert-error')).toBeNull()
  })
})
