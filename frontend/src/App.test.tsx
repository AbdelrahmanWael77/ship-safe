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

  test('all earlier navigation entries are still there, in the same order, with Release assessment added', async () => {
    await start({ [STATUS]: { body: statusConfigured() } })
    expect(primaryNav().getAllByRole('button').map(button => button.textContent?.replace(/\d+$/, ''))).toEqual([
      'Overview', 'Code changes', 'Risk findings', 'Test intelligence', 'Claude Review', 'Release assessment', 'Scan history',
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

    expect(await screen.findByRole('heading', { name: 'Ownership guard appears removed' })).toBeVisible()
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

  test('a review whose scan is stale says so and names the commit it was made for; a current one does not', async () => {
    const binding = { ...pullRequestHistoryItem().binding!, stale: true, stale_at: '2026-11-13T09:00:00+00:00' }
    const reviews = `/api/scans/${report.id}/ai/reviews`
    const api = await start({ [reviews]: { body: [{ ...reviewV2(), scan_binding: binding }] } })
    await userEvent.click(primaryNav().getByRole('button', { name: /Claude Review/ }))
    const alert = await screen.findByRole('alert')
    expect(within(alert).getByRole('heading', { name: /This review is stale/ })).toBeVisible()
    expect(within(alert).getByText('b'.repeat(40))).toBeVisible()
    expect(alert.querySelector('[data-stale]')).toHaveAttribute('data-stale', 'stale-recorded')
    expect(screen.getByRole('heading', { name: 'Ownership guard appears removed' })).toBeVisible()  // still shown, as history
    expect(api.count(reviews)).toBe(1)
  })

  test('a review of a scan that is not stale shows no stale warning', async () => {
    await start({ [`/api/scans/${report.id}/ai/reviews`]: { body: [{ ...reviewV2(), scan_binding: { ...pullRequestHistoryItem().binding!, stale: false } }] } })
    await userEvent.click(primaryNav().getByRole('button', { name: /Claude Review/ }))
    await screen.findByRole('heading', { name: 'Ownership guard appears removed' })
    expect(screen.queryByText(/This review is stale/)).not.toBeInTheDocument()
  })

  test('a v1 review still renders, without the v2-only sections', async () => {
    const { missing_context: _m, ...rest } = reviewV2()
    const { id: _i, status: _s, suggested_validation: _v, proposed_patch: _p, ...finding } = rest.findings[0]
    await start({ [`/api/scans/${report.id}/ai/reviews`]: { body: [{ ...rest, schema_version: 'shipsafe.ai-review.v1', findings: [finding] }] } })
    await userEvent.click(primaryNav().getByRole('button', { name: /Claude Review/ }))
    expect(await screen.findByRole('heading', { name: 'Ownership guard appears removed' })).toBeVisible()
    expect(screen.getByText('SUSPECTED · UNVERIFIED')).toBeVisible()
    expect(screen.queryByText(/How to validate/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Proposed patch/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Context the reviewer did not have/)).not.toBeInTheDocument()
  })
})

describe('Claude Review page: history, side by side, import status', () => {
  const reviews = `/api/scans/${report.id}/ai/reviews`
  const base = (): AIReview => ({
    id: 'current', imported_at: '2026-11-13T12:00:00+00:00', source: 'user_imported_json_unverified_provenance',
    verification_status: 'not_independently_verified', tests_executed: false, schema_version: 'shipsafe.ai-review.v2',
    scan_id: report.id, context_digest: '0'.repeat(64), summary: 'Review of the scan on screen.', recommendation: 'manual_review',
    findings: [
      { id: 'F1', status: 'suspected', title: 'Linked AI finding', severity: 'high', category: 'Authorization', file: report.files[0].path, line: 3,
        evidence: 'evidence', rationale: 'Rationale long enough.', recommendation: 'Do something.', confidence: 'low',
        related_static_finding_ids: [report.findings[0].id], suggested_validation: 'Check it by hand.' },
      { id: 'F2', status: 'suspected', title: 'Extra AI finding', severity: 'low', category: 'Validation', file: report.files[0].path, line: null,
        evidence: 'evidence', rationale: 'Rationale long enough.', recommendation: 'Do something.', confidence: 'low',
        related_static_finding_ids: [], suggested_validation: 'Check it by hand.' },
    ],
    test_ideas: [], limitations: ['No tests were executed.'], missing_context: [],
  })
  const earlier = (): AIReview => ({
    ...base(), id: 'earlier', imported_at: '2026-11-12T12:00:00+00:00', scan_id: 'older-scan', summary: 'Review of an earlier scan.',
    recommendation: 'block_release', findings: [{ ...base().findings[1], title: 'Finding from the earlier scan' }],
    scan_binding: { ...pullRequestHistoryItem().binding!, stale: true, stale_at: '2026-11-13T09:00:00+00:00' }, current_scan: false,
  })
  const openPage = async (routes: Routes) => {
    const api = await start(routes)
    await userEvent.click(primaryNav().getByRole('button', { name: /Claude Review/ }))
    return api
  }
  const history = () => within(screen.getByRole('region', { name: 'Previous reviews' }))
  const compare = () => within(screen.getByRole('region', { name: 'Static scan and imported review' }))

  test('previous reviews list every import; the newest review of this scan is shown by default', async () => {
    await openPage({ [reviews]: { body: [base()] }, [`${reviews}/history`]: { body: [{ ...base(), current_scan: true }, earlier()] } })
    await screen.findByRole('heading', { name: 'Linked AI finding' })
    const rows = history().getAllByRole('row').slice(1)
    expect(rows).toHaveLength(2)
    expect(within(rows[0]).getByText('This scan')).toBeVisible()
    expect(within(rows[0]).getByRole('button', { name: /Shown below/ })).toBeDisabled()
    expect(within(rows[1]).getByText(/Earlier scan · head/)).toBeVisible()
    expect(within(rows[1]).getByText('bbbbbbbbbbbb')).toBeVisible()
    expect(within(rows[1]).getByText('Block release')).toBeVisible()
    expect(rows[1].querySelector('[data-stale]')).toHaveAttribute('data-stale', 'stale-recorded')
    expect(screen.queryByText(/This review is stale/)).not.toBeInTheDocument()
  })

  test('picking an earlier review shows it as stale and as not describing the scan on screen', async () => {
    await openPage({ [reviews]: { body: [base()] }, [`${reviews}/history`]: { body: [{ ...base(), current_scan: true }, earlier()] } })
    await screen.findByRole('heading', { name: 'Linked AI finding' })
    await userEvent.click(history().getByRole('button', { name: /^Show review imported/ }))

    expect(await screen.findByRole('heading', { name: 'Finding from the earlier scan' })).toBeVisible()
    expect(screen.queryByRole('heading', { name: 'Linked AI finding' })).not.toBeInTheDocument()
    expect(within(screen.getByRole('alert')).getByRole('heading', { name: /This review is stale/ })).toBeVisible()
    expect(screen.getByText(/From an earlier scan of this pull request/)).toBeVisible()
    expect(compare().getByText(/belongs to an earlier scan/)).toBeVisible()
    expect(compare().queryByText(report.findings[0].title)).not.toBeInTheDocument()  // not compared with this scan's findings
  })

  test('reviews of earlier scans are listed but never shown by default when this scan has none', async () => {
    await openPage({ [`${reviews}/history`]: { body: [earlier()] } })
    expect(await screen.findByRole('heading', { name: 'No Claude review imported yet' })).toBeVisible()
    expect(history().getAllByRole('row').slice(1)).toHaveLength(1)
    expect(screen.queryByRole('heading', { name: 'Finding from the earlier scan' })).not.toBeInTheDocument()
  })

  test('without the history route the page falls back to the reviews of this scan', async () => {
    await openPage({ [reviews]: { body: [base()] } })
    await screen.findByRole('heading', { name: 'Linked AI finding' })
    expect(history().getAllByRole('row').slice(1)).toHaveLength(1)
    expect(document.querySelector('.alert-error')).toBeNull()
  })

  test('side by side: static suspicions and imported findings are labelled apart and linked by id', async () => {
    await openPage({ [reviews]: { body: [base()] } })
    await screen.findByRole('heading', { name: 'Linked AI finding' })
    const panel = compare()
    expect(panel.getByText('STATIC SUSPICIONS · HEURISTIC SCAN')).toBeVisible()
    expect(panel.getByText('IMPORTED AI FINDINGS · UNVERIFIED')).toBeVisible()
    expect(panel.getByText(/Test evidence: none/)).toBeVisible()
    for (const finding of report.findings) expect(panel.getByText(finding.title)).toBeVisible()
    expect(panel.getAllByText('Referenced by the review')).toHaveLength(1)
    expect(panel.getByText(new RegExp(`relates to static: ${report.findings[0].title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`))).toBeVisible()
    expect(panel.getAllByText('Not in the static scan')).toHaveLength(1)
  })

  test('the source link of an AI finding opens that file in Code changes', async () => {
    await openPage({ [reviews]: { body: [base()] } })
    const card = (await screen.findByRole('heading', { name: 'Linked AI finding' })).closest('.ai-finding') as HTMLElement
    await userEvent.click(within(card).getByRole('button', { name: new RegExp(report.files[0].path.replace(/[.]/g, '\\.')) }))
    expect(await screen.findByRole('region', { name: new RegExp(`Git diff for ${report.files[0].path}`) })).toBeVisible()
  })

  const chooseFile = async (content: string) => {
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    await userEvent.upload(input, new File([content], 'claude-review.json', { type: 'application/json' }))
    await userEvent.click(screen.getByRole('button', { name: /Import review/ }))
  }

  test('a successful import is confirmed next to the control and joins the history', async () => {
    const api = await openPage({ [`POST ${reviews}`]: { status: 201, body: base() } })
    await screen.findByRole('heading', { name: 'No Claude review imported yet' })
    await chooseFile(JSON.stringify({ any: 'json' }))

    const status = await screen.findByRole('status')
    expect(status).toHaveTextContent(/Imported for scan .* 2 proposed findings\. The review is unverified and no tests were run\./)
    expect(status.closest('.ai-step')).not.toBeNull()
    expect(await screen.findByRole('heading', { name: 'Linked AI finding' })).toBeVisible()
    expect(history().getAllByRole('row').slice(1)).toHaveLength(1)
    expect(api.count(`POST ${reviews}`)).toBe(1)
    expect(document.querySelector('.alert-error')).toBeNull()
  })

  test.each([
    [409, 'This review was already imported for this scan. Nothing was added.'],
    [409, 'Review scan ID or context digest does not match this scan. Export a fresh handoff bundle.'],
    [413, 'Review JSON is larger than the 256 KiB import limit'],
    [422, 'Invalid Claude review JSON: 1 validation error'],
  ])('a rejected import (%i) shows the API’s reason next to the control and adds nothing', async (status, detail) => {
    await openPage({ [`POST ${reviews}`]: { status, body: { detail } } })
    await screen.findByRole('heading', { name: 'No Claude review imported yet' })
    await chooseFile('{}')

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(`Not imported: ${detail}`)
    expect(alert.closest('.ai-step')).not.toBeNull()
    expect(screen.getByRole('heading', { name: 'No Claude review imported yet' })).toBeVisible()
    expect(screen.queryByRole('region', { name: 'Previous reviews' })).not.toBeInTheDocument()
    expect(document.querySelector('.alert-error')).toBeNull()
  })

  test('a file over 256 KiB is refused without a request', async () => {
    const api = await openPage({})
    await screen.findByRole('heading', { name: 'No Claude review imported yet' })
    await chooseFile('x'.repeat(256 * 1024 + 1))
    expect(await screen.findByRole('alert')).toHaveTextContent(/too large/)
    expect(api.count(`POST ${reviews}`)).toBe(0)
  })
})
