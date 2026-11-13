import { describe, expect, test, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { deferred, stubApi } from '../test/api'
import type { Routes } from '../test/api'
import { SCAN_ID, headChangedError, notConfiguredError, pullRequestDetail, pullRequestScanReport, statusConfigured, storedScanReport } from '../test/fixtures'
import type { PullRequestDetail } from '../types'
import { getBitbucketStatus } from './client'
import type { BitbucketSelection } from './pages'
import { PrAnalysisPage } from './PrAnalysisPage'
import { useLoad } from './useLoad'

const STATUS = '/api/bitbucket/status'
const DETAIL = '/api/bitbucket/repositories/ledger/pull-requests/7'
const SCAN = `POST ${DETAIL}/scans`
const STORED = `/api/scans/${SCAN_ID}`
const HEAD = 'd'.repeat(40)       // the pull request's head in the detail example
const SCANNED_HEAD = 'b'.repeat(40)
const MERGE_BASE = 'a'.repeat(40)
const error = (status: number, code: string, detail: string) => ({ status, body: { detail, code } })

const navigate = vi.fn()
const onScanned = vi.fn()
const onOpenReport = vi.fn()
function Page({ selection }: { selection: BitbucketSelection }) {
  return <PrAnalysisPage status={useLoad(getBitbucketStatus, 'bitbucket-status')} selection={selection} navigate={navigate} onScanned={onScanned} onOpenReport={onOpenReport} />
}
const SELECTED: BitbucketSelection = { slug: 'ledger', state: 'open', pullRequestId: '7' }
const open = (routes: Routes, selection = SELECTED) => {
  for (const mock of [navigate, onScanned, onOpenReport]) mock.mockClear()
  const api = stubApi({ [STATUS]: { body: statusConfigured() }, [DETAIL]: { body: pullRequestDetail() }, ...routes })
  const view = render(<Page selection={selection} />)
  return { api, view }
}
/** The detail after a scan at the current head: the new scan first, checked and current. */
const detailAfterScan = (): PullRequestDetail => {
  const detail = pullRequestDetail()
  const fresh = { ...detail.scans[0], id: 'new-scan', binding: { ...detail.scans[0].binding, head_commit: HEAD, stale: false, stale_at: null } }
  return { ...detail, scans: [fresh, ...detail.scans] }
}
const unscanned = (): PullRequestDetail => ({ ...pullRequestDetail(), scans: [] })
const lastBody = () => JSON.parse(String(vi.mocked(fetch).mock.calls.filter(call => call[1]?.method === 'POST').slice(-1)[0]?.[1]?.body))

describe('pull request', () => {
  test('shows the pull request, its full head commit, an Open in Bitbucket link and its scans', async () => {
    open({})
    expect(await screen.findByRole('heading', { name: /#7 Change 7/ })).toBeVisible()
    expect(screen.getByText(HEAD)).toBeVisible()
    expect(screen.getByText('c'.repeat(40))).toBeVisible()

    const link = screen.getByRole('link', { name: /Open in Bitbucket/ })
    expect(link).toHaveAttribute('href', 'https://bitbucket.org/acme/ledger/pull-requests/7')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')

    const rows = screen.getAllByRole('row').slice(1)
    expect(rows).toHaveLength(1)
    expect(rows[0].querySelector('[data-stale]')).toHaveAttribute('data-stale', 'stale')
    expect(within(rows[0]).getByText('45/100')).toBeVisible()
    expect(screen.queryByRole('region', { name: 'Scan report' })).not.toBeInTheDocument()
  })

  test('nothing selected: says so and offers the way back, without a request', async () => {
    const { api } = open({}, { slug: null, state: 'open', pullRequestId: null })
    expect(await screen.findByRole('heading', { name: 'No pull request selected' })).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: /Pull requests/ }))
    expect(navigate).toHaveBeenCalledWith('pull-requests')
    expect(api.count(DETAIL)).toBe(0)
  })

  test('a pull request that cannot be scanned says why and disables the scan', async () => {
    const blocked: PullRequestDetail = { ...unscanned(), source_sha: null, scannable: false, not_scannable_code: 'head_commit_unavailable', not_scannable_reason: 'The head commit cannot be read.', stale_checked: false }
    const { api } = open({ [DETAIL]: { body: blocked } })
    expect(await screen.findByText(/cannot be scanned: The head commit cannot be read\./)).toBeVisible()
    expect(screen.getByRole('button', { name: /Scan this pull request/ })).toBeDisabled()
    expect(screen.getByRole('heading', { name: 'Not scanned yet' })).toBeVisible()
    expect(api.calls.some(call => call.startsWith('POST'))).toBe(false)
  })

  test('a failure to load shows the error with Retry; not configured shows the setup message', async () => {
    const first = open({ [DETAIL]: [error(404, 'pull_request_not_found', 'Pull request 7 was not found.'), { body: pullRequestDetail() }] })
    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText('Pull request 7 was not found.')).toBeVisible()
    await userEvent.click(within(alert).getByRole('button', { name: /Retry/ }))
    expect(await screen.findByRole('heading', { name: /#7 Change 7/ })).toBeVisible()
    first.view.unmount()

    open({ [DETAIL]: { status: 503, body: notConfiguredError() } })
    expect(await screen.findByRole('heading', { name: 'Bitbucket is not configured' })).toBeVisible()
  })
})

describe('scanning', () => {
  test('sends the head commit on screen, then shows bound commits, findings and the diff', async () => {
    const report = pullRequestScanReport()
    const { api } = open({ [DETAIL]: [{ body: unscanned() }, { body: detailAfterScan() }], [SCAN]: { status: 201, body: { ...report, id: 'new-scan', binding: { ...report.binding, head_commit: HEAD } } } })
    await userEvent.click(await screen.findByRole('button', { name: /Scan this pull request/ }))

    const region = within(await screen.findByRole('region', { name: 'Scan report' }))
    expect(lastBody()).toEqual({ head_commit: HEAD })
    expect(region.getByText(MERGE_BASE)).toBeVisible()
    expect(region.getByText(HEAD)).toBeVisible()
    expect(region.getByText(/Base commit \(merge base\)/)).toBeVisible()
    for (const finding of report.findings) expect(region.getByText(finding.title)).toBeVisible()
    expect(region.getByRole('region', { name: new RegExp(`Git diff for ${report.files[0].path}`) })).toBeVisible()
    expect(region.getByText(report.disclaimer)).toBeVisible()
    expect(region.getByText('Static suspicions, not verified')).toBeVisible()

    // The scan was compared with Bitbucket by the route that made it.
    await waitFor(() => expect(document.querySelector('.bb-report [data-stale]')).toHaveAttribute('data-stale', 'current'))
    expect(onScanned).toHaveBeenCalledTimes(1)
    expect(api.count(DETAIL)).toBe(2)  // reloaded, so the scan list includes the new scan
    expect(await screen.findByText('Shown below')).toBeVisible()
  })

  test('a finding’s file link and the file list switch the diff', async () => {
    const report = pullRequestScanReport()
    open({ [SCAN]: { status: 201, body: report } })
    await userEvent.click(await screen.findByRole('button', { name: /Scan this pull request/ }))
    const region = within(await screen.findByRole('region', { name: 'Scan report' }))
    const other = report.files.find(file => file.path !== report.files[0].path)
    if (!other) throw new Error('the example report needs two files')

    await userEvent.click(region.getByRole('button', { name: new RegExp(other.path.replace(/[.]/g, '\\.')) , pressed: false }))
    expect(region.getByRole('region', { name: new RegExp(`Git diff for ${other.path}`) })).toBeVisible()
  })

  test('409 head_changed: nothing is shown as scanned, the pull request is reloaded with its new head', async () => {
    const moved = { ...pullRequestDetail(), source_sha: 'e'.repeat(40) }
    const { api } = open({ [DETAIL]: [{ body: pullRequestDetail() }, { body: moved }], [SCAN]: { status: 409, body: headChangedError() } })
    await userEvent.click(await screen.findByRole('button', { name: /Scan this pull request/ }))

    expect(await screen.findByRole('heading', { name: 'The pull request has new commits' })).toBeVisible()
    expect(await screen.findByText('e'.repeat(40))).toBeVisible()
    expect(screen.queryByRole('region', { name: 'Scan report' })).not.toBeInTheDocument()
    expect(onScanned).not.toHaveBeenCalled()
    expect(api.count(DETAIL)).toBe(2)

    // Scanning again sends the new head, not the outdated one.
    api.set(SCAN, { status: 201, body: pullRequestScanReport() })
    await userEvent.click(screen.getByRole('button', { name: /Scan this pull request/ }))
    await screen.findByRole('region', { name: 'Scan report' })
    expect(lastBody()).toEqual({ head_commit: 'e'.repeat(40) })
    expect(screen.queryByRole('heading', { name: 'The pull request has new commits' })).not.toBeInTheDocument()
  })

  test('a failed scan shows the API’s reason and the code, and stores nothing', async () => {
    open({ [SCAN]: error(422, 'diff_too_large', 'Bitbucket could not produce the diff.') })
    await userEvent.click(await screen.findByRole('button', { name: /Scan this pull request/ }))
    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText('The scan failed')).toBeVisible()
    expect(within(alert).getByText('Bitbucket could not produce the diff.')).toBeVisible()
    expect(within(alert).getByText('diff_too_large')).toBeVisible()
    expect(onScanned).not.toHaveBeenCalled()
    expect(screen.queryByRole('region', { name: 'Scan report' })).not.toBeInTheDocument()
  })

  test('shows a scanning state and blocks a second scan meanwhile', async () => {
    const pending = deferred<{ status: number; body: unknown }>()
    const { api } = open({ [SCAN]: () => pending.promise as never })
    await userEvent.click(await screen.findByRole('button', { name: /Scan this pull request/ }))
    expect(await screen.findByRole('heading', { name: /Scanning pull request 7/ })).toBeVisible()
    expect(screen.getByRole('button', { name: /Scanning/ })).toBeDisabled()
    pending.resolve({ status: 201, body: pullRequestScanReport() })
    await screen.findByRole('region', { name: 'Scan report' })
    expect(api.count(SCAN)).toBe(1)
  })
})

describe('stored scans', () => {
  test('View opens a stored scan and keeps the stale state the pull request reported, not "not checked"', async () => {
    const { api } = open({ [STORED]: { body: storedScanReport() } })
    await userEvent.click(await screen.findByRole('button', { name: /^View/ }))
    const region = within(await screen.findByRole('region', { name: 'Scan report' }))
    expect(region.getByText(SCANNED_HEAD)).toBeVisible()
    expect(document.querySelector('.bb-report [data-stale]')).toHaveAttribute('data-stale', 'stale')
    expect(api.count(STORED)).toBe(1)
    expect(api.calls.some(call => call.startsWith('POST'))).toBe(false)

    await userEvent.click(region.getByRole('button', { name: /Open in dashboard/ }))
    expect(onOpenReport).toHaveBeenCalledWith(SCAN_ID)
  })

  test('a report that was cut says it is incomplete', async () => {
    const cut = storedScanReport()
    cut.summary = { ...cut.summary, import_analysis_truncated: true, import_files_skipped: 12 }
    open({ [STORED]: { body: cut } })
    await userEvent.click(await screen.findByRole('button', { name: /^View/ }))
    expect(await screen.findByText(/Incomplete report\..*12 files were not read/)).toBeVisible()
  })

  test('another pull request clears the report of the previous one', async () => {
    const other = { ...unscanned(), id: '8', title: 'Change 8' }
    const { view } = open({ [STORED]: { body: storedScanReport() }, '/api/bitbucket/repositories/ledger/pull-requests/8': { body: other } })
    await userEvent.click(await screen.findByRole('button', { name: /^View/ }))
    await screen.findByRole('region', { name: 'Scan report' })

    view.rerender(<Page selection={{ ...SELECTED, pullRequestId: '8' }} />)
    expect(await screen.findByRole('heading', { name: /#8 Change 8/ })).toBeVisible()
    expect(screen.queryByRole('region', { name: 'Scan report' })).not.toBeInTheDocument()
    expect(screen.queryByText('#7 Change 7')).not.toBeInTheDocument()
  })
})
