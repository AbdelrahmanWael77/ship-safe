// MOCK DATA for the development mock mode (`npm run dev:mock`). Everything in
// this file is invented: the workspace, repositories, people, commits and
// findings do not exist anywhere. It lets the Bitbucket screens be looked at
// without a Bitbucket credential. It is used only through client.ts, only on
// the development server, and never in place of a real answer.
//
// The canned answers follow the API contract (docs/ARCHITECTURE.md,
// "Bitbucket routes") and keep state in memory until the page is reloaded.
import { ApiError } from '../api'
import type {
  Binding, BitbucketRepository, FileChange, Finding, PullRequest, PullRequestDetail, PullRequestList,
  PullRequestListItem, PullRequestScan, PullRequestState, Report,
} from '../types'
import type { BitbucketClient } from './client'

const WORKSPACE = 'mock-workspace'
const PROVIDER = 'bitbucket-cloud'
/** Placeholder commit ids: one hex digit pair repeated, obviously not real. */
const sha = (pair: string) => pair.repeat(20)

const REPOSITORIES: BitbucketRepository[] = [
  { id: `${WORKSPACE}/mock-ledger`, slug: 'mock-ledger', name: 'Mock Ledger', url: `https://bitbucket.org/${WORKSPACE}/mock-ledger`, default_branch: 'main' },
  { id: `${WORKSPACE}/mock-billing`, slug: 'mock-billing', name: 'Mock Billing', url: `https://bitbucket.org/${WORKSPACE}/mock-billing`, default_branch: 'main' },
]

/** What a scan of a mock pull request does. */
type Behaviour = 'findings' | 'clean' | 'too-large' | 'head-moves-once'

interface MockPullRequest extends PullRequest {
  behaviour: Behaviour
  /** Merge base used for the binding of a scan. */
  merge_base: string
}

const pullRequest = (
  slug: string, id: string, title: string, state: PullRequestState, source_ref: string, author: string | null,
  heads: { source: string | null; target: string | null; base: string }, behaviour: Behaviour, updated_at: string,
): MockPullRequest => ({
  provider: PROVIDER, repository_id: `${WORKSPACE}/${slug}`, id, title, state, source_ref, target_ref: 'main',
  source_sha: heads.source, target_sha: heads.target, author,
  url: `https://bitbucket.org/${WORKSPACE}/${slug}/pull-requests/${id}`, updated_at, behaviour, merge_base: heads.base,
})

const FINDINGS: Finding[] = [
  {
    id: 'mock-finding-1', category: 'authorization', severity: 'high', title: 'Mock finding: permission check removed',
    file: 'ledger/refunds.py', line: 12, status: 'suspected', evidence: '-    require_role(user, "finance")',
    explanation: 'Canned example. A role check present before the change is absent after it.',
    recommendation: 'Canned example. Confirm the check moved elsewhere, and add a regression test.',
  },
  {
    id: 'mock-finding-2', category: 'money', severity: 'medium', title: 'Mock finding: rounding changed',
    file: 'ledger/refunds.py', line: 21, status: 'suspected', evidence: '+    return round(amount, 1)',
    explanation: 'Canned example. The number of decimal places used for a money amount changed.',
    recommendation: 'Canned example. Check the amount against the currency’s minor unit.',
  },
]

const FILES_WITH_FINDINGS: FileChange[] = [{
  path: 'ledger/refunds.py', status: 'modified', additions: 2, deletions: 2, changed_functions: ['issue_refund'],
  diff: [
    'diff --git a/ledger/refunds.py b/ledger/refunds.py', '--- a/ledger/refunds.py', '+++ b/ledger/refunds.py',
    '@@ -10,6 +10,6 @@ def issue_refund(user, amount):', '     """MOCK DATA: canned diff, not real code."""',
    '-    require_role(user, "finance")', '+    log.info("refund requested")', '     amount = Decimal(amount)',
    '-    return round(amount, 2)', '+    return round(amount, 1)',
  ].join('\n'),
  diff_truncated: false, diff_lines_omitted: 0,
}]

const FILES_CLEAN: FileChange[] = [{
  path: 'docs/release-checklist.md', status: 'modified', additions: 1, deletions: 0, changed_functions: [],
  diff: [
    'diff --git a/docs/release-checklist.md b/docs/release-checklist.md', '--- a/docs/release-checklist.md',
    '+++ b/docs/release-checklist.md', '@@ -3,3 +3,4 @@', ' ## Before release', ' - run the suite',
    '+- MOCK DATA: canned line, not a real change',
  ].join('\n'),
  diff_truncated: false, diff_lines_omitted: 0,
}]

function createState() {
  const pulls: MockPullRequest[] = [
    pullRequest('mock-ledger', '101', 'Tighten refund rounding', 'open', 'feature/refund-rounding', 'Mock Author A', { source: sha('1a'), target: sha('10'), base: sha('0a') }, 'findings', '2026-11-12T09:30:00+00:00'),
    pullRequest('mock-ledger', '102', 'Session token refresh', 'open', 'feature/token-refresh', 'Mock Author B', { source: sha('2b'), target: sha('10'), base: sha('0b') }, 'findings', '2026-11-12T14:05:00+00:00'),
    pullRequest('mock-ledger', '103', 'Docs: release checklist', 'open', 'docs/release-checklist', 'Mock Author A', { source: sha('3c'), target: sha('10'), base: sha('0c') }, 'clean', '2026-11-11T16:45:00+00:00'),
    pullRequest('mock-ledger', '104', 'Fork contribution: CSV export', 'open', 'csv-export', 'Mock Outside Contributor', { source: null, target: sha('10'), base: sha('0d') }, 'findings', '2026-11-10T11:20:00+00:00'),
    pullRequest('mock-ledger', '105', 'Vendor bundle update', 'open', 'chore/vendor-bundle', 'Mock Author C', { source: sha('5e'), target: sha('10'), base: sha('0e') }, 'too-large', '2026-11-09T08:00:00+00:00'),
    pullRequest('mock-ledger', '106', 'Hotfix: currency parsing', 'open', 'hotfix/currency-parsing', null, { source: sha('6f'), target: sha('10'), base: sha('0f') }, 'head-moves-once', '2026-11-13T07:15:00+00:00'),
    pullRequest('mock-ledger', '90', 'Add ledger export endpoint', 'merged', 'feature/ledger-export', 'Mock Author B', { source: sha('9a'), target: sha('10'), base: sha('09') }, 'clean', '2026-11-05T10:00:00+00:00'),
    pullRequest('mock-ledger', '88', 'Experiment: new tax tables', 'declined', 'experiment/tax-tables', 'Mock Author C', { source: sha('8b'), target: sha('10'), base: sha('08') }, 'findings', '2026-11-03T10:00:00+00:00'),
  ]
  const reports: Report[] = []
  let counter = 0

  const stored = (pull: MockPullRequest, head: string, created_at: string): Report => {
    const clean = pull.behaviour === 'clean'
    const files = structuredClone(clean ? FILES_CLEAN : FILES_WITH_FINDINGS)
    const findings = clean ? [] : structuredClone(FINDINGS)
    counter += 1
    return {
      id: `mock-scan-${String(counter).padStart(4, '0')}`, created_at, repo_name: `${REPOSITORIES.find(r => r.id === pull.repository_id)?.name} (MOCK)`,
      repository_path: `https://bitbucket.org/${pull.repository_id}`, base_ref: pull.target_ref, head_ref: pull.source_ref,
      base_sha: pull.merge_base.slice(0, 12), head_sha: head.slice(0, 12), duration_ms: 3,
      summary: {
        files_changed: files.length, lines_added: files.reduce((sum, file) => sum + file.additions, 0),
        lines_removed: files.reduce((sum, file) => sum + file.deletions, 0), finding_count: findings.length,
        risk_score: clean ? 3 : 41, recommendation: clean ? 'Low risk signals' : 'Manual review recommended',
        test_status: 'not_run', truncated: false, files_omitted: 0,
      },
      files, findings, affected_modules: [], test_suggestions: [],
      disclaimer: 'MOCK DATA. This report is a canned example from the development mock mode. Nothing was read from Bitbucket and nothing was analysed.',
      binding: {
        provider: PROVIDER, repository_id: pull.repository_id, pull_request_id: pull.id, base_commit: pull.merge_base,
        head_commit: head, comparison: 'merge-base', stale: false, stale_at: null, stale_checked: false,
      },
      mock: true,
    }
  }

  // Two pull requests start with a scan: #102 scanned at an older head (so it
  // is stale), #103 scanned at its current head.
  reports.push(stored(pulls[1], sha('2a'), '2026-11-12T11:00:00+00:00'))
  reports.push(stored(pulls[2], sha('3c'), '2026-11-11T17:00:00+00:00'))
  return { pulls, reports, headMoved: false, stored }
}

// Created on first use, so the module has no side effect and a production build can drop it.
let created: ReturnType<typeof createState> | null = null
const current = () => (created ??= createState())
/** Forget every mock scan (tests call this; in the browser a page reload does the same). */
export const resetMock = () => { created = null }

/** Long enough to see the loading states, short enough not to annoy. */
export const MOCK_DELAY_MS = 350
const answer = <T,>(make: () => T): Promise<T> => new Promise((resolve, reject) => {
  setTimeout(() => { try { resolve(structuredClone(make())) } catch (error) { reject(error) } }, MOCK_DELAY_MS)
})

const repository = (slug: string) => {
  const found = REPOSITORIES.find(item => item.slug === slug)
  if (!found) throw new ApiError(`MOCK: no approved repository "${slug}".`, 404, 'repository_not_found')
  return found
}
const find = (slug: string, id: string) => {
  const found = current().pulls.find(item => item.repository_id === repository(slug).id && item.id === id)
  if (!found) throw new ApiError(`MOCK: pull request ${id} was not found.`, 404, 'pull_request_not_found')
  return found
}

/** The binding as a route that just compared with the pull request's head would return it. */
const checkedBinding = (report: Report, pull: MockPullRequest): Binding => {
  const binding = report.binding as Binding
  if (!pull.source_sha) return { ...binding, stale_checked: false }
  const stale = binding.head_commit !== pull.source_sha
  return { ...binding, stale, stale_at: stale ? '2026-11-12T14:05:00+00:00' : null, stale_checked: true }
}
const scansOf = (pull: MockPullRequest): PullRequestScan[] => current().reports
  .filter(report => report.binding?.repository_id === pull.repository_id && report.binding?.pull_request_id === pull.id)
  .sort((a, b) => b.created_at.localeCompare(a.created_at))
  .map(report => ({ id: report.id, created_at: report.created_at, summary: report.summary, binding: checkedBinding(report, pull) }))

const publicFields = ({ behaviour: _behaviour, merge_base: _base, ...rest }: MockPullRequest): PullRequest => rest

export const mockClient: BitbucketClient = {
  getBitbucketStatus: () => answer(() => ({
    configured: true, provider: PROVIDER, workspace: WORKSPACE, repositories: REPOSITORIES.map(item => item.slug),
  })),

  listRepositories: () => answer(() => REPOSITORIES),

  listPullRequests: (slug, wanted) => answer((): PullRequestList => {
    const found = repository(slug)
    const pull_requests = current().pulls.filter(item => item.repository_id === found.id && item.state === wanted).map((pull): PullRequestListItem => {
      const scans = scansOf(pull)
      // Like the real list: full SHAs only for pull requests that already have scans.
      const known = scans.length > 0
      return {
        ...publicFields(pull), source_sha: known ? pull.source_sha : null, target_sha: known ? pull.target_sha : null,
        scan_count: scans.length, latest_scan: scans[0] ?? null, stale_checked: known && pull.source_sha !== null,
      }
    })
    return { repository: found, state: wanted, pull_requests, truncated: false }
  }),

  getPullRequest: (slug, id) => answer((): PullRequestDetail => {
    const pull = find(slug, id)
    const blocked = pull.source_sha === null
    return {
      ...publicFields(pull), repository: repository(slug), scannable: !blocked,
      not_scannable_code: blocked ? 'head_commit_unavailable' : null,
      not_scannable_reason: blocked ? 'MOCK: the pull request comes from a fork, so its head commit cannot be read through the approved repository.' : null,
      stale_checked: !blocked, scans: scansOf(pull),
    }
  }),

  scanPullRequest: (slug, id, headCommit) => answer((): Report => {
    const pull = find(slug, id)
    if (!pull.source_sha) throw new ApiError('MOCK: the pull request’s head commit cannot be read (fork).', 409, 'head_commit_unavailable')
    if (pull.behaviour === 'head-moves-once' && !current().headMoved) {
      current().headMoved = true
      pull.source_sha = sha('7f')
    }
    if (headCommit && headCommit !== pull.source_sha) {
      throw new ApiError('The pull request has new commits since it was loaded. Reload it and scan again.', 409, 'head_changed')
    }
    if (pull.behaviour === 'too-large') throw new ApiError('MOCK: Bitbucket could not produce the diff because it is too large.', 422, 'diff_too_large')
    const report = current().stored(pull, pull.source_sha, new Date().toISOString())
    current().reports.push(report)
    return { ...report, binding: checkedBinding(report, pull) }
  }),

  getScan: id => answer((): Report => {
    const report = current().reports.find(item => item.id === id)
    if (!report) throw new ApiError('MOCK: scan report not found.', 404)
    return report
  }),
}
