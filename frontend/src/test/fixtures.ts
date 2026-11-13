// Typed views of the published contract examples. The backend test
// `test_published_example_responses_match_the_current_contract` keeps
// docs/example-bitbucket-responses.json in step with the real API, so
// frontend tests that use these are tied to the real response shapes.
// The data is MOCK (workspace "acme", placeholder SHAs), not live Bitbucket.
import examples from '../../../docs/example-bitbucket-responses.json'
import report from '../../../docs/example-scan-report.json'
import type { Binding, BitbucketRepository, BitbucketStatus, DemoInfo, PullRequestDetail, PullRequestList, Report, ScanHistory } from '../types'

const example = <T,>(prefix: string): T => {
  const found = Object.entries(examples).find(([key]) => key.startsWith(prefix))
  if (!found) throw new Error(`No example response starts with "${prefix}"`)
  return structuredClone(found[1]) as T
}

export const statusConfigured = () => example<BitbucketStatus>('GET /api/bitbucket/status')
export const statusNotConfigured = (): BitbucketStatus => ({ configured: false, provider: null, workspace: null, repositories: [] })
export const repositories = () => example<BitbucketRepository[]>('GET /api/bitbucket/repositories')
export const notConfiguredError = () => example<{ detail: string; code: string }>('Any /api/bitbucket/* data route when not configured')

// -- the existing demo dashboard ---------------------------------------------
export const demoReport = () => structuredClone(report) as unknown as Report
export const demoInfo = (): DemoInfo => ({
  repository_path: '/demo/ledgerlite', name: 'LedgerLite (synthetic)', base_ref: 'main',
  default_head: 'feature/release-candidate', branches: [], note: 'Synthetic demo repository',
})
export const demoHistory = (): ScanHistory[] => {
  const { id, created_at, repo_name, base_ref, head_ref, duration_ms, summary } = demoReport()
  return [{ id, created_at, repo_name, base_ref, head_ref, duration_ms, summary }]
}

/** The answers the dashboard needs to start in the local demo. */
export const demoRoutes = () => ({
  '/api/demo': { body: demoInfo() },
  '/api/scans?limit=100': { body: demoHistory() },
  [`/api/scans/${report.id}`]: { body: demoReport() },
  [`/api/scans/${report.id}/ai/reviews`]: { body: [] },
})

// -- pull requests (same published examples) ---------------------------------
export const SCAN_ID = '36667b1c-2bd4-48e4-971f-cd972b008e00'
export const pullRequestsBeforeScan = () => example<PullRequestList>('GET /api/bitbucket/repositories/ledger/pull-requests (before any scan)')
export const pullRequestsAfterHeadMoved = () => example<PullRequestList>('GET /api/bitbucket/repositories/ledger/pull-requests (after the head moved)')
/** Pull request 7 with one stored scan that is stale (its head moved to dddd…). */
export const pullRequestDetail = () => example<PullRequestDetail>('GET /api/bitbucket/repositories/ledger/pull-requests/7 (after the head moved)')
export const headChangedError = () => example<{ detail: string; code: string }>('POST .../pull-requests/7/scans with an outdated head_commit')
/** A full report (the published scan report example) with the binding the scan route returns. */
export const pullRequestScanReport = (): Report => {
  const { binding } = example<{ binding: Binding }>('POST /api/bitbucket/repositories/ledger/pull-requests/7/scans')
  return { ...demoReport(), id: SCAN_ID, binding }
}
/** The same report as the stored-scan route returns it: never compared with Bitbucket. */
export const storedScanReport = (): Report => {
  const report = pullRequestScanReport()
  return { ...report, binding: { ...(report.binding as Binding), stale_checked: false } }
}
export const pullRequestHistoryItem = () => example<ScanHistory>('GET /api/scans (history item')
