// Development mock mode. The mode is switched on here by stubbing Vite's
// MODE; `fetch` is stubbed with an empty table so any Bitbucket request that
// escaped the mock would be counted.
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from '../App'
import { isApiError } from '../api'
import { stubApi } from '../test/api'
import { demoRoutes } from '../test/fixtures'
import { getBitbucketStatus, getPullRequest, isMockMode, listPullRequests, listRepositories, scanPullRequest } from './client'
import { resetMock } from './mock'

beforeEach(() => { resetMock() })
afterEach(() => { vi.unstubAllEnvs() })
const mockMode = () => vi.stubEnv('MODE', 'mock')
const bitbucketCalls = (calls: string[]) => calls.filter(call => call.includes('/api/bitbucket'))

describe('mock mode switch', () => {
  test('is off unless the development server runs in mode "mock"', () => {
    expect(isMockMode()).toBe(false)
    mockMode()
    expect(isMockMode()).toBe(true)
    vi.stubEnv('DEV', false)  // a production build
    expect(isMockMode()).toBe(false)
  })

  test('off: the real route is called and a failure is never replaced by canned data', async () => {
    const api = stubApi({})
    await expect(listRepositories()).rejects.toMatchObject({ status: 404 })
    expect(api.calls).toEqual(['/api/bitbucket/repositories'])
  })

  test('on: no Bitbucket route is called and every answer is labelled as mock', async () => {
    mockMode()
    const api = stubApi({})
    expect((await getBitbucketStatus()).workspace).toBe('mock-workspace')
    const repositories = await listRepositories()
    expect(repositories.every(item => item.id.startsWith('mock-workspace/'))).toBe(true)
    const report = await scanPullRequest('mock-ledger', '101', null)
    expect(report.mock).toBe(true)
    expect(report.disclaimer).toMatch(/^MOCK DATA/)
    expect(api.calls).toEqual([])
  })
})

describe('mock answers follow the contract', () => {
  beforeEach(() => { mockMode(); stubApi({}) })

  test('a new scan is current; a scan of an older head is stale; the list gives SHAs only for scanned pull requests', async () => {
    const before = await listPullRequests('mock-ledger', 'open')
    const find = (id: string, list = before) => list.pull_requests.find(item => item.id === id)
    expect(find('101')).toMatchObject({ scan_count: 0, latest_scan: null, source_sha: null, stale_checked: false })
    expect(find('102')?.latest_scan?.binding).toMatchObject({ stale: true, stale_checked: true })
    expect(find('103')?.latest_scan?.binding).toMatchObject({ stale: false, stale_checked: true })

    const detail = await getPullRequest('mock-ledger', '101')
    const report = await scanPullRequest('mock-ledger', '101', detail.source_sha)
    expect(report.binding).toMatchObject({ head_commit: detail.source_sha, comparison: 'merge-base', stale: false, stale_checked: true })
    expect(find('101', await listPullRequests('mock-ledger', 'open'))?.scan_count).toBe(1)
  })

  test('refusals use the API’s codes: fork, moved head, oversized diff, unknown ids', async () => {
    expect((await getPullRequest('mock-ledger', '104')).scannable).toBe(false)
    await expect(scanPullRequest('mock-ledger', '104', null)).rejects.toSatisfy(error => isApiError(error, 'head_commit_unavailable'))
    const moving = await getPullRequest('mock-ledger', '106')
    await expect(scanPullRequest('mock-ledger', '106', moving.source_sha)).rejects.toSatisfy(error => isApiError(error, 'head_changed'))
    const reloaded = await getPullRequest('mock-ledger', '106')
    expect(reloaded.source_sha).not.toBe(moving.source_sha)
    expect((await scanPullRequest('mock-ledger', '106', reloaded.source_sha)).mock).toBe(true)
    await expect(scanPullRequest('mock-ledger', '105', null)).rejects.toSatisfy(error => isApiError(error, 'diff_too_large'))
    await expect(getPullRequest('mock-ledger', '999')).rejects.toSatisfy(error => isApiError(error, 'pull_request_not_found'))
    await expect(listPullRequests('nope', 'open')).rejects.toSatisfy(error => isApiError(error, 'repository_not_found'))
  })
})

describe('dashboard', () => {
  test('outside mock mode there is no banner', async () => {
    stubApi(demoRoutes())
    render(<App />)
    await screen.findByRole('heading', { name: 'Release overview' })
    expect(screen.queryByText('MOCK DATA')).not.toBeInTheDocument()
  })

  test('mock mode: the MOCK DATA banner stays on every page, and a pull request can be scanned end to end', async () => {
    mockMode()
    const api = stubApi(demoRoutes())
    render(<App />)
    // Mock mode fakes only the Bitbucket screens: the invented "configured" status must not
    // switch the dashboard to live mode, so the synthetic demo stays available (docs/DEMO_SCRIPT.md)
    // and invented data is never labelled as live Bitbucket.
    await screen.findByRole('heading', { name: 'Release overview' })
    expect(screen.getByText('LOCAL DEMO')).toBeVisible()
    expect(screen.queryByText(/BITBUCKET LIVE/)).not.toBeInTheDocument()
    const banner = () => screen.getByText('MOCK DATA', { selector: '.mock-banner strong' })
    expect(banner()).toBeVisible()

    const nav = within(screen.getByRole('navigation', { name: 'Bitbucket navigation' }))
    await userEvent.click(nav.getByRole('button', { name: 'Pull requests' }))
    await userEvent.click(await screen.findByRole('button', { name: /Analyze pull request 101/ }, { timeout: 3000 }))
    expect(nav.getByRole('button', { name: 'Pull requests' })).toHaveClass('active')  // PR analysis belongs to it
    await userEvent.click(await screen.findByRole('button', { name: /Scan this pull request/ }, { timeout: 3000 }))

    const report = within(await screen.findByRole('region', { name: 'Scan report' }, { timeout: 3000 }))
    expect(report.getByText('MOCK DATA')).toBeVisible()
    expect(report.getByText('Mock finding: permission check removed')).toBeVisible()
    expect(report.queryByRole('button', { name: /Open in dashboard/ })).not.toBeInTheDocument()  // a mock scan is not in the database
    expect(banner()).toBeVisible()
    expect(bitbucketCalls(api.calls)).toEqual([])
  })
})
