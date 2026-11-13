// The dashboard as a whole: the existing demo flow (which must keep working
// exactly as before the Bitbucket screens) and navigation into the Bitbucket
// section. `fetch` is stubbed; nothing leaves jsdom.
import { describe, expect, test } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from './App'
import { networkDown, stubApi } from './test/api'
import type { Routes } from './test/api'
import { demoReport, demoRoutes, repositories, statusConfigured, statusNotConfigured } from './test/fixtures'

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
  test('the sidebar has a Bitbucket group with Repositories', async () => {
    await start({ [STATUS]: { body: statusConfigured() } })
    expect(bitbucketNav().getAllByRole('button').map(button => button.textContent)).toEqual(['Repositories'])
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
    expect(bitbucketNav().getByText('Off')).toBeVisible()

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
