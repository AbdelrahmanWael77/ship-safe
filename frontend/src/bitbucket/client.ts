// Calls to the read-only Bitbucket routes of the ShipSafe API. The browser
// never talks to Bitbucket and never holds a credential: the server does.
// Contract: docs/ARCHITECTURE.md, "Bitbucket routes".
//
// Development mock mode (`npm run dev:mock`): every function here answers
// from the canned data in mock.ts instead, and the dashboard shows a
// permanent MOCK DATA banner. The two sources are never mixed: in mock mode
// no Bitbucket route is called, and outside it no canned answer is ever used,
// not even when a real request fails.
import { api } from '../api'
import type { BitbucketRepository, BitbucketStatus, PullRequestDetail, PullRequestList, PullRequestState, Report } from '../types'
import { mockClient } from './mock'

/**
 * True only on the Vite development server started with `--mode mock`.
 * `import.meta.env.DEV` is the constant `false` in a production build, so a
 * build can never be in mock mode, whatever mode name it is given.
 */
export const isMockMode = (): boolean => import.meta.env.DEV && import.meta.env.MODE === 'mock'

export interface BitbucketClient {
  getBitbucketStatus: () => Promise<BitbucketStatus>
  listRepositories: () => Promise<BitbucketRepository[]>
  listPullRequests: (slug: string, state: PullRequestState) => Promise<PullRequestList>
  getPullRequest: (slug: string, id: string) => Promise<PullRequestDetail>
  scanPullRequest: (slug: string, id: string, headCommit: string | null) => Promise<Report>
  getScan: (id: string) => Promise<Report>
}

const pullRequests = (slug: string) => `/api/bitbucket/repositories/${encodeURIComponent(slug)}/pull-requests`

const realClient: BitbucketClient = {
  getBitbucketStatus: () => api<BitbucketStatus>('/api/bitbucket/status'),
  listRepositories: () => api<BitbucketRepository[]>('/api/bitbucket/repositories'),
  listPullRequests: (slug, state) => api<PullRequestList>(`${pullRequests(slug)}?state=${state}`),
  getPullRequest: (slug, id) => api<PullRequestDetail>(`${pullRequests(slug)}/${encodeURIComponent(id)}`),
  // `head_commit` is the head the person is looking at: the API refuses the
  // scan with 409 `head_changed` if the pull request has moved on since.
  scanPullRequest: (slug, id, headCommit) => api<Report>(`${pullRequests(slug)}/${encodeURIComponent(id)}/scans`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(headCommit ? { head_commit: headCommit } : {}),
  }),
  getScan: id => api<Report>(`/api/scans/${encodeURIComponent(id)}`),
}

// Written so a production build drops mock.ts: `import.meta.env.DEV` is
// replaced by `false` there, which leaves `realClient` as the only branch.
const client = (): BitbucketClient => (import.meta.env.DEV && isMockMode() ? mockClient : realClient)

/** Whether the server has Bitbucket settings. Does not contact Bitbucket. */
export const getBitbucketStatus = () => client().getBitbucketStatus()

/** The approved repositories, as Bitbucket currently returns them. */
export const listRepositories = () => client().listRepositories()

/** Up to 200 pull requests of one repository in one state. */
export const listPullRequests = (slug: string, state: PullRequestState) => client().listPullRequests(slug, state)

/** One pull request with full SHAs, whether it can be scanned, and its scans. */
export const getPullRequest = (slug: string, id: string) => client().getPullRequest(slug, id)

/** Scan a pull request from its merge base to `headCommit` (reads only). */
export const scanPullRequest = (slug: string, id: string, headCommit: string | null) => client().scanPullRequest(slug, id, headCommit)

/** A stored scan report. This route never contacts Bitbucket, so its binding is "not checked". */
export const getScan = (id: string) => client().getScan(id)
