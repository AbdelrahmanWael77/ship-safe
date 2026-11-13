import { AlertCircle, RefreshCw } from 'lucide-react'
import { ApiError } from '../api'

// What the person can do about each failure. The API's own message is always
// shown as well; these only add the next step. Codes: docs/ARCHITECTURE.md.
const HINTS: Record<string, string> = {
  bitbucket_auth_failed: 'The Bitbucket credential on the ShipSafe server was rejected. Someone with access to the server must check SHIPSAFE_BITBUCKET_TOKEN (and SHIPSAFE_BITBUCKET_EMAIL), then restart the API. This cannot be fixed from the browser.',
  bitbucket_unavailable: 'Bitbucket did not answer in time or is limiting requests. Wait a moment, then retry.',
  bitbucket_error: 'Bitbucket returned something ShipSafe did not expect. Retry; if it keeps happening, check the API log.',
  repository_not_allowed: 'This repository is not on the server’s approved list (SHIPSAFE_BITBUCKET_REPOSITORIES).',
  pull_request_not_found: 'Bitbucket has no such pull request in this repository. Go back to the list and refresh it.',
  head_commit_unavailable: 'The pull request’s head commit cannot be read through the approved repository (for example a pull request from a fork). ShipSafe refuses to scan it.',
  base_commit_unavailable: 'The commit the pull request branched from cannot be read, so there is nothing to compare with. ShipSafe refuses to scan it.',
  commit_not_found: 'A commit of this pull request no longer exists in Bitbucket. Reload the pull request.',
  diff_too_large: 'Bitbucket would not produce a diff this large. ShipSafe has no per-file fallback, so this pull request cannot be scanned.',
  repository_not_found: 'Bitbucket has no such repository in the configured workspace, or the credential cannot see it.',
}

/** A failed request, with the API's message, a next step and a Retry button. */
export function ErrorPanel({ title, error, onRetry }: { title: string; error: Error; onRetry: () => void }) {
  const code = error instanceof ApiError ? error.code : null
  const hint = error instanceof ApiError && error.status === 0 ? null : code ? HINTS[code] : null
  return (
    <div className="panel bb-state bb-error" role="alert">
      <AlertCircle size={22} />
      <div>
        <h3>{title}</h3>
        <p className="bb-error-message">{error.message}</p>
        {hint && <p>{hint}</p>}
        {code && <p className="bb-error-code">Error code: <code>{code}</code></p>}
      </div>
      <button className="secondary-button" onClick={onRetry}><RefreshCw size={15} /> Retry</button>
    </div>
  )
}
