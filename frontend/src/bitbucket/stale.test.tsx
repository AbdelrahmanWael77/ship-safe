import { describe, expect, test } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { Binding } from '../types'
import examples from '../../../docs/example-bitbucket-responses.json'
import { StaleBadge } from './StaleBadge'
import { staleDisplay, staleStatus } from './stale'

const pullRequestScan = (stale: boolean, stale_checked: boolean, stale_at: string | null = stale ? '2026-11-12T12:00:00+00:00' : null): Binding => ({
  provider: 'bitbucket-cloud', repository_id: 'acme/ledger', pull_request_id: '7',
  base_commit: 'a'.repeat(40), head_commit: 'b'.repeat(40), comparison: 'merge-base', stale, stale_at, stale_checked,
})
const localScan: Binding = { ...pullRequestScan(false, false), provider: 'local-git', pull_request_id: null, comparison: 'direct' }

describe('staleStatus()', () => {
  test.each([
    [true, true, 'stale'],
    [false, true, 'current'],
    [true, false, 'stale-recorded'],
    [false, false, 'unchecked'],
  ] as const)('stale=%s, stale_checked=%s → %s', (stale, checked, expected) => {
    expect(staleStatus(pullRequestScan(stale, checked))).toBe(expected)
  })

  test('does not apply to local scans, missing bindings, or old exports', () => {
    expect(staleStatus(localScan)).toBe('not-applicable')
    expect(staleStatus({ ...localScan, stale_checked: true })).toBe('not-applicable')
    expect(staleStatus(undefined)).toBe('not-applicable')
    expect(staleStatus(null)).toBe('not-applicable')
  })
})

describe('staleDisplay()', () => {
  test('only a scan checked in this response is ever called Current', () => {
    expect(staleDisplay(pullRequestScan(false, true))?.label).toBe('Current')
    for (const binding of [pullRequestScan(false, false), pullRequestScan(true, false), pullRequestScan(true, true)]) {
      expect(staleDisplay(binding)?.label).not.toBe('Current')
    }
  })

  test('labels and colours', () => {
    expect(staleDisplay(pullRequestScan(true, true))).toMatchObject({ label: 'Stale', kind: 'danger' })
    expect(staleDisplay(pullRequestScan(true, false))).toMatchObject({ label: 'Stale', kind: 'danger' })
    expect(staleDisplay(pullRequestScan(false, false))).toMatchObject({ label: 'Not checked', kind: 'muted' })
    expect(staleDisplay(pullRequestScan(false, true))).toMatchObject({ label: 'Current', kind: 'good' })
    expect(staleDisplay(localScan)).toBeNull()
  })

  test('a recorded-stale scan says it was not re-checked; a checked one says it was', () => {
    expect(staleDisplay(pullRequestScan(true, false))?.description).toMatch(/not re-checked/)
    expect(staleDisplay(pullRequestScan(true, true))?.description).toMatch(/^Checked against Bitbucket just now/)
    expect(staleDisplay(pullRequestScan(false, false))?.description).toMatch(/may have new commits/)
  })

  test('a missing or malformed stale_at does not break the text', () => {
    expect(staleDisplay(pullRequestScan(true, false, null))?.description).toBe('Recorded as stale; not re-checked just now. Open the pull request to check again.')
    expect(staleDisplay(pullRequestScan(true, true, 'not a date'))?.description).not.toMatch(/Invalid Date/)
  })
})

describe('<StaleBadge />', () => {
  test.each([
    [pullRequestScan(false, true), 'Current', 'current', 'pill-good'],
    [pullRequestScan(true, true), 'Stale', 'stale', 'pill-danger'],
    [pullRequestScan(true, false), 'Stale', 'stale-recorded', 'pill-danger'],
    [pullRequestScan(false, false), 'Not checked', 'unchecked', 'pill-muted'],
  ] as const)('%#: shows "%s"', (binding, label, status, className) => {
    const { container } = render(<StaleBadge binding={binding} />)
    const badge = container.querySelector('.stale-badge') as HTMLElement
    expect(badge).toHaveTextContent(label)
    expect(badge).toHaveAttribute('data-stale', status)
    expect(badge).toHaveClass('pill', className)
    expect(badge).toHaveAttribute('title', staleDisplay(binding)!.description)
  })

  test('renders nothing for a local scan or a report without a binding', () => {
    expect(render(<StaleBadge binding={localScan} />).container).toBeEmptyDOMElement()
    expect(render(<StaleBadge binding={undefined} />).container).toBeEmptyDOMElement()
  })

  test('an unchecked scan is never presented as current', () => {
    render(<StaleBadge binding={pullRequestScan(false, false)} />)
    expect(screen.queryByText('Current')).not.toBeInTheDocument()
    expect(screen.getByText('Not checked')).toBeVisible()
  })
})

describe('against the published example responses', () => {
  // docs/example-bitbucket-responses.json is the contract the backend tests guard.
  const find = (prefix: string) => Object.entries(examples).find(([key]) => key.startsWith(prefix))![1] as any

  test('a history item that was not checked shows Not checked, not Current', () => {
    const item = find('GET /api/scans (history item')
    expect([item.binding.stale, item.binding.stale_checked]).toEqual([false, false])
    expect(staleStatus(item.binding)).toBe('unchecked')
  })

  test('the pull request detail after the head moved shows its scan as Stale, checked', () => {
    const detail = find('GET /api/bitbucket/repositories/ledger/pull-requests/7 (after the head moved)')
    expect(detail.stale_checked).toBe(true)
    expect(staleStatus(detail.scans[0].binding)).toBe('stale')
  })

  test('the scan response itself is Current', () => {
    expect(staleStatus(find('POST /api/bitbucket/').binding)).toBe('current')
  })

  test('every binding in the examples has exactly the fields the Binding type declares', () => {
    const fields = Object.keys(pullRequestScan(false, false)).sort()
    const bindings: unknown[] = []
    const walk = (value: unknown) => {
      if (Array.isArray(value)) value.forEach(walk)
      else if (value && typeof value === 'object') {
        for (const [key, child] of Object.entries(value)) key === 'binding' ? bindings.push(child) : walk(child)
      }
    }
    walk(examples)
    expect(bindings.length).toBeGreaterThanOrEqual(4)
    for (const binding of bindings) expect(Object.keys(binding as object).sort()).toEqual(fields)
  })
})
