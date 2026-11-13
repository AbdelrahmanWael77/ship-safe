// One place that decides how a scan's stale state is shown. The API gives
// two booleans; the dashboard must never show a scan as current unless this
// very response compared it with Bitbucket (see docs/ARCHITECTURE.md,
// "Stale state — how to read it").
import type { Binding } from '../types'

export type StaleStatus =
  | 'current'         // checked now, matches the pull request head
  | 'stale'           // checked now, the pull request has moved on
  | 'stale-recorded'  // recorded stale earlier, not re-checked in this response
  | 'unchecked'       // not known to be stale, and not checked in this response
  | 'not-applicable'  // not a pull request scan: stale does not apply

export function staleStatus(binding: Binding | null | undefined): StaleStatus {
  if (!binding || binding.pull_request_id == null) return 'not-applicable'
  if (binding.stale) return binding.stale_checked ? 'stale' : 'stale-recorded'
  return binding.stale_checked ? 'current' : 'unchecked'
}

export interface StaleDisplay {
  label: string
  /** Pill colour class suffix from styles.css. */
  kind: 'good' | 'danger' | 'warning' | 'muted'
  /** Longer explanation, used as the tooltip and by screen readers. */
  description: string
}

const when = (iso: string | null) => {
  if (!iso) return null
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? null : date.toLocaleString()
}

/** Null for scans that stale does not apply to (local scans). */
export function staleDisplay(binding: Binding | null | undefined): StaleDisplay | null {
  const since = when(binding?.stale_at ?? null)
  switch (staleStatus(binding)) {
    case 'current':
      return { label: 'Current', kind: 'good', description: 'Checked against Bitbucket just now: this scan matches the pull request’s head commit.' }
    case 'stale':
      return { label: 'Stale', kind: 'danger', description: `Checked against Bitbucket just now: the pull request has new commits since this scan${since ? ` (first noticed ${since})` : ''}. Scan again.` }
    case 'stale-recorded':
      return { label: 'Stale', kind: 'danger', description: `Recorded as stale${since ? ` on ${since}` : ''}; not re-checked just now. Open the pull request to check again.` }
    case 'unchecked':
      return { label: 'Not checked', kind: 'muted', description: 'Not compared with Bitbucket in this view, so the pull request may have new commits. Open the pull request to check.' }
    default:
      return null
  }
}
