import { CheckCircle2, PlugZap, RefreshCw } from 'lucide-react'
import type { BitbucketStatus } from '../types'
import { ErrorPanel } from './ErrorPanel'
import type { Loaded } from './useLoad'

/**
 * What GET /api/bitbucket/status says. That route reports the server's
 * settings only; it does not contact Bitbucket, so "configured" here never
 * means the credential works. The repository list is the first real call.
 */
export function ConnectionStatus({ status }: { status: Loaded<BitbucketStatus> }) {
  if (status.loading && !status.data) {
    return <div className="panel bb-state" role="status"><div className="spinner bb-spinner" /><div><h3>Checking the Bitbucket configuration…</h3></div></div>
  }
  if (status.error) {
    return <ErrorPanel title="Could not read the Bitbucket configuration" error={status.error} onRetry={status.reload} />
  }
  if (!status.data) return null
  if (!status.data.configured) return <NotConfigured onRetry={status.reload} />
  const { workspace, repositories } = status.data
  return (
    <div className="panel bb-state bb-configured" role="status">
      <CheckCircle2 size={22} />
      <div>
        <h3>Bitbucket is configured <span className="pill pill-good">READ-ONLY</span></h3>
        <p>Workspace <code>{workspace}</code> · {repositories.length} approved {repositories.length === 1 ? 'repository' : 'repositories'}. ShipSafe only reads from Bitbucket; it never writes, merges or approves.</p>
      </div>
    </div>
  )
}

/** Shown wherever a Bitbucket screen cannot work because the server has no settings. */
export function NotConfigured({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="panel bb-state bb-not-configured" role="status">
      <PlugZap size={22} />
      <div>
        <h3>Bitbucket is not configured</h3>
        <p>The ShipSafe server has no Bitbucket settings, so there are no repositories to show. The local demo keeps working without them.</p>
        <p>To turn it on, someone with access to the server sets these in its local <code>.env</code> file and restarts the API:</p>
        <ul className="bb-setup-list">
          <li><code>SHIPSAFE_BITBUCKET_WORKSPACE</code></li>
          <li><code>SHIPSAFE_BITBUCKET_REPOSITORIES</code></li>
          <li><code>SHIPSAFE_BITBUCKET_TOKEN</code></li>
        </ul>
        <p className="bb-warning">The token is a secret. It belongs on the server only: never in this browser, a <code>VITE_</code> variable, a chat, or Git.</p>
      </div>
      <button className="secondary-button" onClick={onRetry}><RefreshCw size={15} /> Check again</button>
    </div>
  )
}
