import { ExternalLink, FolderGit2, RefreshCw } from 'lucide-react'
import { isApiError } from '../api'
import type { BitbucketStatus } from '../types'
import { listRepositories } from './client'
import { ConnectionStatus, NotConfigured } from './ConnectionStatus'
import { ErrorPanel } from './ErrorPanel'
import type { Loaded } from './useLoad'
import { useLoad } from './useLoad'

/**
 * The approved Bitbucket repositories. Only what GET /api/bitbucket/repositories
 * returns is listed as a repository; the configured slugs from the status
 * route are used solely to point out ones Bitbucket did not return.
 */
export function RepositoriesPage({ status }: { status: Loaded<BitbucketStatus> }) {
  const configured = status.data?.configured === true
  const repositories = useLoad(listRepositories, 'repositories', configured)

  // The server lost its settings between the status call and this one.
  const notConfiguredNow = isApiError(repositories.error, 'bitbucket_not_configured')
  const reloadAll = () => { status.reload(); repositories.reload() }

  if (!configured || notConfiguredNow) {
    return notConfiguredNow ? <NotConfigured onRetry={reloadAll} /> : <ConnectionStatus status={status} />
  }

  const returned = repositories.data ?? []
  const missing = (status.data?.repositories ?? []).filter(slug => !returned.some(repository => repository.slug === slug))

  return (
    <>
      <ConnectionStatus status={status} />
      {repositories.loading && !repositories.data && (
        <div className="panel bb-state" role="status"><div className="spinner bb-spinner" /><div><h3>Loading repositories from Bitbucket…</h3></div></div>
      )}
      {repositories.error && <ErrorPanel title="Could not load the repositories" error={repositories.error} onRetry={repositories.reload} />}
      {repositories.data && (
        <div className="panel">
          <div className="panel-head">
            <div><h3>Approved repositories</h3><p>Returned by Bitbucket just now. Repositories outside the server’s approved list are never shown.</p></div>
            <div className="bb-head-actions">
              <span className="pill pill-muted">{returned.length} {returned.length === 1 ? 'repository' : 'repositories'}</span>
              <button className="secondary-button" onClick={repositories.reload} disabled={repositories.loading}>
                <RefreshCw size={15} className={repositories.loading ? 'spin' : ''} /> Refresh
              </button>
            </div>
          </div>
          {returned.length === 0 ? (
            <div className="empty-state">
              <h3>Bitbucket returned no approved repositories</h3>
              <p>None of the repositories on the server’s approved list was found in workspace <code>{status.data?.workspace}</code>. Check the slugs in <code>SHIPSAFE_BITBUCKET_REPOSITORIES</code> and that the credential can read them.</p>
            </div>
          ) : (
            <div className="history-table-wrap">
              <table className="history-table bb-table">
                <thead><tr><th>Repository</th><th>Identifier</th><th>Default branch</th><th><span className="visually-hidden">Links</span></th></tr></thead>
                <tbody>
                  {returned.map(repository => (
                    <tr key={repository.id}>
                      <td><span className="bb-repo-name"><FolderGit2 size={16} /> <strong>{repository.name}</strong></span></td>
                      <td><code>{repository.id}</code></td>
                      <td>{repository.default_branch ? <code>{repository.default_branch}</code> : <span className="bb-muted">Not reported</span>}</td>
                      <td>
                        <a className="table-action" href={repository.url} target="_blank" rel="noopener noreferrer">
                          Open in Bitbucket <ExternalLink size={13} /><span className="visually-hidden"> (opens in a new tab)</span>
                        </a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {missing.length > 0 && returned.length > 0 && (
            <p className="bb-footnote" role="note">
              {missing.length === 1 ? 'One approved repository was' : `${missing.length} approved repositories were`} not returned by Bitbucket: {missing.map((slug, index) => <span key={slug}>{index > 0 && ', '}<code>{slug}</code></span>)}. Check the slug and the credential’s access.
            </p>
          )}
        </div>
      )}
    </>
  )
}
