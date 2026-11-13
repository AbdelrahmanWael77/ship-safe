import { useState } from 'react'
import { AlertTriangle, ArrowRight, ChevronDown, ExternalLink, FolderGit2, GitPullRequest, RefreshCw, Search } from 'lucide-react'
import { isApiError } from '../api'
import type { BitbucketStatus, PullRequestListItem, PullRequestState } from '../types'
import { listPullRequests, listRepositories } from './client'
import { ConnectionStatus, NotConfigured } from './ConnectionStatus'
import { ErrorPanel } from './ErrorPanel'
import type { BitbucketNavigate, BitbucketSelection } from './pages'
import { StaleBadge } from './StaleBadge'
import type { Loaded } from './useLoad'
import { useLoad } from './useLoad'

const STATES: { id: PullRequestState; label: string }[] = [
  { id: 'open', label: 'Open' },
  { id: 'merged', label: 'Merged' },
  { id: 'declined', label: 'Declined' },
]

/** The API returns at most this many pull requests per state (MAX_PULL_REQUESTS in the backend). */
const LIST_LIMIT = 200

const matches = (item: PullRequestListItem, query: string) =>
  [item.title, item.author ?? '', item.source_ref, item.target_ref].some(text => text.toLowerCase().includes(query))

const updated = (iso: string | null) => {
  if (!iso) return 'Not reported'
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? 'Not reported' : date.toLocaleString()
}

/**
 * Pull requests of one approved repository, in one state, as
 * GET /api/bitbucket/repositories/{slug}/pull-requests returns them. The state
 * filter is asked of the API; the search box only narrows what was returned.
 */
export function PullRequestsPage({ status, selection, navigate }: {
  status: Loaded<BitbucketStatus>
  selection: BitbucketSelection
  navigate: BitbucketNavigate
}) {
  const configured = status.data?.configured === true
  const repositories = useLoad(listRepositories, 'repositories', configured)
  const [query, setQuery] = useState('')

  const available = repositories.data ?? []
  // The remembered repository if Bitbucket still returns it, else the first one.
  const slug = available.find(repository => repository.slug === selection.slug)?.slug ?? available[0]?.slug ?? null
  const state = selection.state
  const list = useLoad(() => listPullRequests(slug as string, state), `pull-requests:${slug}:${state}`, configured && slug !== null)
  // While another repository or state is loading, the previous answer must not be shown as if it were the new one.
  const shown = list.data && list.data.repository.slug === slug && list.data.state === state ? list.data : null

  const notConfiguredNow = isApiError(repositories.error, 'bitbucket_not_configured') || isApiError(list.error, 'bitbucket_not_configured')
  if (!configured || notConfiguredNow) {
    return notConfiguredNow
      ? <NotConfigured onRetry={() => { status.reload(); repositories.reload(); list.reload() }} />
      : <ConnectionStatus status={status} />
  }
  if (repositories.loading && !repositories.data) {
    return <div className="panel bb-state" role="status"><div className="spinner bb-spinner" /><div><h3>Loading repositories from Bitbucket…</h3></div></div>
  }
  if (repositories.error) return <ErrorPanel title="Could not load the repositories" error={repositories.error} onRetry={repositories.reload} />
  if (slug === null) {
    return (
      <div className="panel"><div className="empty-state">
        <h3>Bitbucket returned no approved repositories</h3>
        <p>There is no repository to list pull requests for. Check the Repositories page.</p>
        <p><button className="secondary-button" onClick={() => navigate('repositories')}><FolderGit2 size={15} /> Open Repositories</button></p>
      </div></div>
    )
  }

  const all = shown?.pull_requests ?? []
  const needle = query.trim().toLowerCase()
  const visible = needle ? all.filter(item => matches(item, needle)) : all
  const stateLabel = STATES.find(item => item.id === state)?.label.toLowerCase()

  return (
    <>
      <div className="panel bb-toolbar">
        <label className="bb-field">
          <span className="micro-label">REPOSITORY</span>
          <span className="select-shell">
            <FolderGit2 size={16} />
            <select aria-label="Repository" value={slug} onChange={event => navigate('pull-requests', { slug: event.target.value, pullRequestId: null })}>
              {available.map(repository => <option key={repository.id} value={repository.slug}>{repository.id}</option>)}
            </select>
            <ChevronDown size={15} />
          </span>
        </label>
        <div className="bb-field">
          <span className="micro-label" id="bb-state-label">STATE</span>
          <div className="bb-segments" role="group" aria-labelledby="bb-state-label">
            {STATES.map(item => (
              <button key={item.id} className={`bb-segment ${state === item.id ? 'active' : ''}`} aria-pressed={state === item.id} onClick={() => navigate('pull-requests', { state: item.id })}>{item.label}</button>
            ))}
          </div>
        </div>
        <label className="bb-field bb-field-grow">
          <span className="micro-label">SEARCH</span>
          <span className="search-field">
            <Search size={16} />
            <input type="search" aria-label="Search pull requests" placeholder="Title, author, source or target branch…" value={query} onChange={event => setQuery(event.target.value)} />
          </span>
        </label>
        <button className="secondary-button" onClick={list.reload} disabled={list.loading}>
          <RefreshCw size={15} className={list.loading ? 'spin' : ''} /> Refresh
        </button>
      </div>

      {list.loading && !shown && (
        <div className="panel bb-state" role="status"><div className="spinner bb-spinner" /><div><h3>Loading {stateLabel} pull requests from Bitbucket…</h3><p>Pull requests that already have scans are compared with Bitbucket, which can take a moment.</p></div></div>
      )}
      {list.error && <ErrorPanel title="Could not load the pull requests" error={list.error} onRetry={list.reload} />}
      {shown && shown.truncated && (
        <div className="panel bb-state bb-warning-panel" role="status">
          <AlertTriangle size={22} />
          <div>
            <h3>Only the first {LIST_LIMIT} {stateLabel} pull requests are shown</h3>
            <p>Bitbucket has more {stateLabel} pull requests in this repository than ShipSafe lists. The rest cannot be listed or searched here; the search box only looks through the {all.length} that were returned.</p>
          </div>
        </div>
      )}
      {shown && (
        <div className="panel">
          <div className="panel-head">
            <div><h3>{STATES.find(item => item.id === state)?.label} pull requests · <code>{shown.repository.id}</code></h3><p>Returned by Bitbucket just now, read-only. A scan is “current” only when it was compared with Bitbucket in this list.</p></div>
            <span className="pill pill-muted">{needle ? `${visible.length} of ${all.length}` : all.length} {all.length === 1 ? 'pull request' : 'pull requests'}{shown.truncated ? ' (first 200)' : ''}</span>
          </div>
          {all.length === 0 ? (
            <div className="empty-state"><h3>No {stateLabel} pull requests</h3><p>Bitbucket returned no {stateLabel} pull requests for <code>{shown.repository.id}</code>. Try another state or repository.</p></div>
          ) : visible.length === 0 ? (
            <div className="empty-state">
              <h3>No pull request matches “{query.trim()}”</h3>
              <p>The search looks at the title, author, source branch and target branch of the {all.length} returned pull requests.</p>
              <p><button className="secondary-button" onClick={() => setQuery('')}>Clear search</button></p>
            </div>
          ) : (
            <div className="history-table-wrap">
              <table className="history-table bb-table">
                <thead><tr><th>Pull request</th><th>Branches</th><th>Updated</th><th>Scans</th><th>Latest scan</th><th><span className="visually-hidden">Actions</span></th></tr></thead>
                <tbody>
                  {visible.map(item => (
                    <tr key={item.id}>
                      <td>
                        <div className="comparison-cell"><GitPullRequest size={18} /><div>
                          <strong>#{item.id} {item.title}</strong>
                          <small>{item.author ?? 'Author not reported'}</small>
                        </div></div>
                      </td>
                      <td><code>{item.source_ref}</code> → <code>{item.target_ref}</code></td>
                      <td>{updated(item.updated_at)}</td>
                      <td>{item.scan_count === 0 ? <span className="bb-muted">Not scanned</span> : `${item.scan_count} ${item.scan_count === 1 ? 'scan' : 'scans'}`}</td>
                      <td>
                        {item.latest_scan ? (
                          <span className="bb-latest">
                            <StaleBadge binding={item.latest_scan.binding} />
                            <small>{item.latest_scan.summary.finding_count} static {item.latest_scan.summary.finding_count === 1 ? 'finding' : 'findings'} · static risk {item.latest_scan.summary.risk_score}/100</small>
                          </span>
                        ) : <span className="bb-muted">—</span>}
                      </td>
                      <td>
                        <span className="bb-row-actions">
                          <button className="table-action" onClick={() => navigate('pr-analysis', { slug, pullRequestId: item.id })}>
                            Analyze<span className="visually-hidden"> pull request {item.id}</span> <ArrowRight size={14} />
                          </button>
                          <a className="table-action" href={item.url} target="_blank" rel="noopener noreferrer">
                            Open in Bitbucket <ExternalLink size={13} /><span className="visually-hidden"> (pull request {item.id}, opens in a new tab)</span>
                          </a>
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </>
  )
}
