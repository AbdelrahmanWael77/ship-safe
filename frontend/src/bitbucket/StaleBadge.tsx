import type { Binding } from '../types'
import { staleDisplay, staleStatus } from './stale'

/** Current / Stale / Not checked. Renders nothing for scans stale does not apply to. */
export function StaleBadge({ binding }: { binding: Binding | null | undefined }) {
  const display = staleDisplay(binding)
  if (!display) return null
  return (
    <span className={`pill pill-${display.kind} stale-badge`} data-stale={staleStatus(binding)} title={display.description}>
      <span className="pill-dot" />{display.label}
      <span className="visually-hidden">. {display.description}</span>
    </span>
  )
}
