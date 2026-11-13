// The dashboard as a whole: the existing demo flow (which must keep working
// exactly as before the Bitbucket screens) and navigation into the Bitbucket
// section. `fetch` is stubbed; nothing leaves jsdom.
import { describe, expect, test } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from './App'
import { networkDown, stubApi } from './test/api'
import type { Routes } from './test/api'
import type { AIReview } from './types'
import { SCAN_ID, demoHistory, demoReport, demoRoutes, pullRequestDetail, pullRequestHistoryItem, pullRequestScanReport, pullRequestsBeforeScan, repositories, statusConfigured, statusNotConfigured, storedScanReport } from './test/fixtures'

const STATUS = '/api/bitbucket/status'
const REPOS = '/api/bitbucket/repositories'
const report = demoReport()

async function start(routes: Routes = {}) {
  const api = stubApi({ ...demoRoutes(), ...routes })
  render(<App />)
  await screen.findByRole('heading', { name: 'Release overview' })
  return api
}
const primaryNav = () => within(screen.getByRole('navigation', { name: 'Primary navigation' }))
const bitbucketNav = () => within(screen.getByRole('navigation', { name: 'Bitbucket navigation' }))

describe('existing demo dashboard', () => {
  test('the overview loads the latest stored scan', async () => {
    const api = await start()
    expect(screen.getByText('LOCAL DEMO')).toBeVisible()
    expect(screen.getByText(report.base_sha)).toBeVisible()
    expect(screen.getByText(report.head_sha)).toBeVisible()
    expect(screen.getByText('Requires engineering review')).toBeVisible()  // finding_count > 0
    expect(screen.getByText(report.summary.recommendation)).toBeVisible()
    expect(api.calls).toEqual(expect.arrayContaining(['/api/demo', '/api/scans', `/api/scans/${report.id}`]))
  })

  test('the sidebar switches between the existing pages', async () => {
    await start()
    const user = userEvent.setup()

    await user.click(primaryNav().getByRole('button', { name: /Risk findings/ }))
    for (const finding of report.findings) expect(await screen.findByText(finding.title)).toBeInTheDocument()

    await user.click(primaryNav().getByRole('button', { name: /Scan history/ }))
    expect(await screen.findByRole('heading', { name: 'Recent analyses' })).toBeInTheDocument()
    expect(screen.getByText('1 saved')).toBeVisible()

    await user.click(primaryNav().getByRole('button', { name: /Overview/ }))
    expect(await screen.findByRole('heading', { name: 'Release overview' })).toBeInTheDocument()
  })

  test('all existing navigation entries are still there, in the same order', async () => {
    await start({ [STATUS]: { body: statusConfigured() } })
    expect(primaryNav().getAllByRole('button').map(button => button.textContent?.replace(/\d+$/, ''))).toEqual([
      'Overview', 'Code changes', 'Risk findings', 'Test intelligence', 'Claude Review', 'Scan history',
    ])
    expect(screen.getByRole('button', { name: 'Configuration' })).toBeVisible()
  })

  test.each([
    ['is not configured', { body: statusNotConfigured() }],
    ['status cannot be read (older backend: 404)', { status: 404, body: { detail: 'Not Found' } }],
    ['status request fails on the network', networkDown],
  ])('the demo is unaffected when Bitbucket %s', async (_name, answer) => {
    await start({ [STATUS]: answer })
    expect(screen.getByText('LOCAL DEMO')).toBeVisible()
    expect(screen.getByText(report.summary.recommendation)).toBeVisible()
    expect(document.querySelector('.alert-error')).toBeNull()  // no error banner for a Bitbucket problem
  })
})

describe('Bitbucket navigation', () => {
  test('the sidebar has a Bitbucket group with Repositories and Pull requests', async () => {
    await start({ [STATUS]: { body: statusConfigured() } })
    expect(bitbucketNav().getAllByRole('button').map(button => button.textContent)).toEqual(['Repositories', 'Pull requests'])
  })

  test('the status is asked once at start; repositories are not loaded until the page is opened', async () => {
    const api = await start({ [STATUS]: { body: statusConfigured() }, [REPOS]: { body: repositories() } })
    expect([api.count(STATUS), api.count(REPOS)]).toEqual([1, 0])
  })

  test('opening Repositories shows the Bitbucket page, marks it active and names it in the top bar', async () => {
    const api = await start({ [STATUS]: { body: statusConfigured() }, [REPOS]: { body: repositories() } })
    const entry = bitbucketNav().getByRole('button', { name: 'Repositories' })
    await userEvent.click(entry)

    const section = within(screen.getByRole('region', { name: 'Bitbucket' }))
    expect(section.getByRole('heading', { level: 1, name: /Repositories/ })).toBeVisible()
    expect(section.getByText('BITBUCKET / REPOSITORIES')).toBeVisible()
    expect(await section.findByText('acme/ledger')).toBeVisible()
    expect(entry).toHaveClass('active')
    expect(primaryNav().getByRole('button', { name: /Overview/ })).not.toHaveClass('active')
    expect(document.querySelector('.topbar-left strong')).toHaveTextContent('Repositories')
    expect(screen.queryByRole('heading', { name: 'Release overview' })).not.toBeInTheDocument()
    expect([api.count(STATUS), api.count(REPOS)]).toEqual([1, 1])
  })

  test('going back to the overview restores the demo exactly', async () => {
    await start({ [STATUS]: { body: statusConfigured() }, [REPOS]: { body: repositories() } })
    await userEvent.click(bitbucketNav().getByRole('button', { name: 'Repositories' }))
    await screen.findByText('acme/ledger')
    await userEvent.click(primaryNav().getByRole('button', { name: /Overview/ }))

    expect(await screen.findByRole('heading', { name: 'Release overview' })).toBeVisible()
    expect(screen.getByText('LOCAL DEMO')).toBeVisible()
    expect(screen.queryByRole('region', { name: 'Bitbucket' })).not.toBeInTheDocument()
    expect(document.querySelector('.topbar-left strong')).toHaveTextContent('Overview')
  })

  test('configured: no "Off" tag on the navigation entry', async () => {
    await start({ [STATUS]: { body: statusConfigured() } })
    expect(bitbucketNav().queryByText('Off')).not.toBeInTheDocument()
  })

  test('not configured: the entry is tagged "Off" and the page explains the setup', async () => {
    const api = await start({ [STATUS]: { body: statusNotConfigured() } })
    expect(bitbucketNav().getAllByText('Off')).toHaveLength(2)  // both entries

    await userEvent.click(bitbucketNav().getByRole('button', { name: /Repositories/ }))
    expect(await screen.findByRole('heading', { name: 'Bitbucket is not configured' })).toBeVisible()
    expect(api.count(REPOS)).toBe(0)
  })

  test('status unknown: no tag is shown, and the page offers Retry', async () => {
    await start({ [STATUS]: [networkDown, { body: statusConfigured() }], [REPOS]: { body: repositories() } })
    expect(bitbucketNav().queryByText('Off')).not.toBeInTheDocument()  // unknown is not shown as "off"

    await userEvent.click(bitbucketNav().getByRole('button', { name: 'Repositories' }))
    await userEvent.click(within(await screen.findByRole('alert')).getByRole('button', { name: /Retry/ }))
    expect(await screen.findByText('acme/ledger')).toBeVisible()
  })
})

describe('pull requests in the dashboard', () => {
  const LIST = '/api/bitbucket/repositories/ledger/pull-requests?state=open'
  const DETAIL = '/api/bitbucket/repositories/ledger/pull-requests/7'
  const configured = () => ({ [STATUS]: { body: statusConfigured() }, [REPOS]: { body: repositories() }, [LIST]: { body: pullRequestsBeforeScan() }, [DETAIL]: { body: pullRequestDetail() } })

  test('repository → pull request → scan → report; the history is refreshed and the selection survives leaving', async () => {
    const api = await start({ ...configured(), [`POST ${DETAIL}/scans`]: { status: 201, body: pullRequestScanReport() } })
    const user = userEvent.setup()
    await user.click(bitbucketNav().getByRole('button', { name: 'Pull requests' }))
    await user.click(await screen.findByRole('button', { name: /Analyze pull request 7/ }))

    expect(document.querySelector('.topbar-left strong')).toHaveTextContent('PR analysis')
    expect(bitbucketNav().getByRole('button', { name: 'Pull requests' })).toHaveClass('active')
    const historyCalls = api.count('/api/scans')
    await user.click(await screen.findByRole('button', { name: /Scan this pull request/ }))
    expect(await screen.findByRole('region', { name: 'Scan report' })).toBeVisible()
    expect(api.count('/api/scans')).toBe(historyCalls + 1)

    await user.click(within(screen.getByRole('region', { name: 'Bitbucket' })).getByRole('button', { name: 'Pull requests' }))
    expect(await screen.findByText('#7 Change 7')).toBeVisible()
    expect(document.querySelector('.alert-error')).toBeNull()
  })

  test('the scan history marks a pull request scan and never shows it as current', async () => {
    await start({ ...configured(), '/api/scans': { body: [...demoHistory(), pullRequestHistoryItem()] } })
    await userEvent.click(primaryNav().getByRole('button', { name: /Scan history/ }))
    const row = (await screen.findByText(/Bitbucket · acme\/ledger · PR #7/)).closest('tr') as HTMLElement
    expect(row.querySelector('[data-stale]')).toHaveAttribute('data-stale', 'unchecked')
    expect(document.querySelectorAll('[data-stale]')).toHaveLength(1)  // local scans have no stale state
  })

  test('"Open in dashboard" loads the stored scan into the existing pages', async () => {
    await start({ ...configured(), [`/api/scans/${SCAN_ID}`]: { body: storedScanReport() }, [`/api/scans/${SCAN_ID}/ai/reviews`]: { body: [] } })
    const user = userEvent.setup()
    await user.click(bitbucketNav().getByRole('button', { name: 'Pull requests' }))
    await user.click(await screen.findByRole('button', { name: /Analyze pull request 7/ }))
    await user.click(await screen.findByRole('button', { name: /^View/ }))
    await user.click(await screen.findByRole('button', { name: /Open in dashboard/ }))
    expect(await screen.findByRole('heading', { name: 'Release overview' })).toBeVisible()
    expect(screen.getByText(/Loaded saved scan from/)).toBeVisible()
  })

  test('a Bitbucket pull request scan is never labelled as the local demo; it shows its repository, PR and commits', async () => {
    await start({ ...configured(), '/api/scans': { body: [pullRequestHistoryItem(), ...demoHistory()] }, [`/api/scans/${SCAN_ID}`]: { body: storedScanReport() }, [`/api/scans/${SCAN_ID}/ai/reviews`]: { body: [] } })
    expect(screen.queryByText('LOCAL DEMO')).not.toBeInTheDocument()
    expect(screen.queryByText('LIVE DEMO')).not.toBeInTheDocument()
    expect(screen.queryByText(/LedgerLite/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Synthetic demo repository/)).not.toBeInTheDocument()
    expect(screen.getByText('BITBUCKET · READ-ONLY')).toBeVisible()
    expect(screen.getByText('BITBUCKET SCAN')).toBeVisible()

    const source = within(screen.getByRole('region', { name: 'Scan source' }))
    expect(source.getByRole('heading', { name: /Bitbucket pull request #7/ })).toBeVisible()
    expect(source.getByText('acme/ledger')).toBeVisible()
    expect(source.getByText('a'.repeat(40))).toBeVisible()
    expect(source.getByText('b'.repeat(40))).toBeVisible()
    expect(source.getByText(/Base \(merge base\)/)).toBeVisible()
    expect(document.querySelector('.bb-source [data-stale]')).toHaveAttribute('data-stale', 'unchecked')  // a stored scan is never "current"

    await userEvent.click(source.getByRole('button', { name: /Open pull request/ }))
    expect(await screen.findByRole('heading', { name: /#7 Change 7/ })).toBeVisible()
  })

  test('opening a demo scan from the history brings the demo labels back', async () => {
    await start({ ...configured(), '/api/scans': { body: [pullRequestHistoryItem(), ...demoHistory()] }, [`/api/scans/${SCAN_ID}`]: { body: storedScanReport() }, [`/api/scans/${SCAN_ID}/ai/reviews`]: { body: [] } })
    await userEvent.click(primaryNav().getByRole('button', { name: /Scan history/ }))
    const demoRow = (await screen.findAllByRole('row')).find(row => !row.textContent?.includes('PR #7') && within(row).queryByRole('button', { name: /Open/ })) as HTMLElement
    await userEvent.click(within(demoRow).getByRole('button', { name: /Open/ }))

    expect(await screen.findByText('LOCAL DEMO')).toBeVisible()
    expect(screen.getByText('LIVE DEMO')).toBeVisible()
    expect(screen.getByText('LedgerLite project')).toBeVisible()
    expect(screen.queryByRole('region', { name: 'Scan source' })).not.toBeInTheDocument()
    expect(screen.queryByText('BITBUCKET · READ-ONLY')).not.toBeInTheDocument()
  })
})

describe('Claude review package export', () => {
  const openReview = async () => { await userEvent.click(primaryNav().getByRole('button', { name: /Claude Review/ })) }
  const context = (required: boolean) => ({ [`/api/scans/${report.id}/ai/context`]: { body: { scan_id: report.id, context_digest: '0'.repeat(64), review_count: 0, acknowledgement_required: required } } })

  test('the synthetic demo exports without a confirmation', async () => {
    await start(context(false))
    await openReview()
    const link = await screen.findByRole('link', { name: /Download handoff ZIP/ })
    expect(link).toHaveAttribute('href', `/api/scans/${report.id}/ai/handoff`)
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  })

  test.each([
    ['the API says a confirmation is required', context(true)],
    ['the API cannot say (request fails)', {}],
  ])('no download until source sharing is confirmed when %s', async (_name, routes) => {
    await start(routes)
    await openReview()
    const box = await screen.findByRole('checkbox')
    expect(screen.getByRole('button', { name: /Download handoff ZIP/ })).toBeDisabled()
    expect(screen.queryByRole('link', { name: /Download handoff ZIP/ })).not.toBeInTheDocument()

    await userEvent.click(box)
    expect(screen.getByRole('link', { name: /Download handoff ZIP/ })).toHaveAttribute('href', `/api/scans/${report.id}/ai/handoff?acknowledge_source_sharing=true`)
    expect(document.querySelector('.alert-error')).toBeNull()
  })
})

describe('imported Claude review (schema v2)', () => {
  const reviewV2 = (): AIReview => ({
    id: 'r1', imported_at: '2026-11-13T10:00:00+00:00', source: 'user_imported_json_unverified_provenance',
    verification_status: 'not_independently_verified', tests_executed: false, schema_version: 'shipsafe.ai-review.v2',
    scan_id: report.id, context_digest: '0'.repeat(64), summary: 'Synthetic fixture review.', recommendation: 'manual_review',
    findings: [{
      id: 'F1', status: 'suspected', title: 'Ownership guard appears removed', severity: 'high', category: 'Authorization',
      file: report.files[0].path, line: null, evidence: 'guard removed', rationale: 'The check is gone from the diff.',
      recommendation: 'Restore the check.', confidence: 'medium', related_static_finding_ids: [],
      suggested_validation: 'Read another user’s invoice as a second user; expect a refusal.',
      proposed_patch: '+    require_owner(user)\n<img src=x onerror="window.__xss = 1">',
    }],
    test_ideas: [], limitations: ['No tests were executed.'], missing_context: ['Callers were not included.'],
  })

  test('shows the id, how to validate, the proposed patch as inert text, and the missing context, all as unverified', async () => {
    await start({ [`/api/scans/${report.id}/ai/reviews`]: { body: [reviewV2()] } })
    await userEvent.click(primaryNav().getByRole('button', { name: /Claude Review/ }))

    expect(await screen.findByText('Ownership guard appears removed')).toBeVisible()
    expect(screen.getByText('F1')).toBeVisible()
    expect(screen.getByText('SUSPECTED · UNVERIFIED')).toBeVisible()
    expect(screen.getByText('UNVERIFIED AI SUGGESTIONS')).toBeVisible()
    expect(screen.getByText(/How to validate \(not done\)/)).toBeVisible()
    expect(screen.getByText(/Read another user’s invoice/)).toBeVisible()
    expect(screen.getByText(/Proposed patch · unverified · not applied by ShipSafe/)).toBeVisible()
    expect(screen.getByText(/require_owner\(user\)/)).toBeVisible()
    expect(screen.getByText('Callers were not included.')).toBeVisible()
    // Imported text is rendered as text: no element is created from it.
    expect(document.querySelector('.ai-patch img')).toBeNull()
    expect((window as unknown as { __xss?: number }).__xss).toBeUndefined()
  })

  test('a v1 review still renders, without the v2-only sections', async () => {
    const { missing_context: _m, ...rest } = reviewV2()
    const { id: _i, status: _s, suggested_validation: _v, proposed_patch: _p, ...finding } = rest.findings[0]
    await start({ [`/api/scans/${report.id}/ai/reviews`]: { body: [{ ...rest, schema_version: 'shipsafe.ai-review.v1', findings: [finding] }] } })
    await userEvent.click(primaryNav().getByRole('button', { name: /Claude Review/ }))
    expect(await screen.findByText('Ownership guard appears removed')).toBeVisible()
    expect(screen.getByText('SUSPECTED · UNVERIFIED')).toBeVisible()
    expect(screen.queryByText(/How to validate/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Proposed patch/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Context the reviewer did not have/)).not.toBeInTheDocument()
  })
})
