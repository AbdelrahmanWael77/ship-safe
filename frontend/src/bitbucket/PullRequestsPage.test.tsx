import { useState } from 'react'
import { describe, expect, test, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { deferred, stubApi } from '../test/api'
import type { Routes } from '../test/api'
import { notConfiguredError, pullRequestsAfterHeadMoved, pullRequestsBeforeScan, repositories, statusConfigured, statusNotConfigured } from '../test/fixtures'
import type { PullRequestList } from '../types'
import { getBitbucketStatus } from './client'
import type { BitbucketNavigate, BitbucketSelection } from './pages'
import { INITIAL_SELECTION } from './pages'
import { PullRequestsPage } from './PullRequestsPage'
import { useLoad } from './useLoad'

const STATUS = '/api/bitbucket/status'
const REPOS = '/api/bitbucket/repositories'
const list = (state = 'open', slug = 'ledger') => `/api/bitbucket/repositories/${slug}/pull-requests?state=${state}`
const error = (status: number, code: string, detail: string) => ({ status, body: { detail, code } })

const navigated = vi.fn()
// Holds the selection the way App does, and records where the page asked to go.
function Page() {
  const [selection, setSelection] = useState<BitbucketSelection>(INITIAL_SELECTION)
  const navigate: BitbucketNavigate = (page, change) => { navigated(page, change); if (change) setSelection(previous => ({ ...previous, ...change })) }
  return <PullRequestsPage status={useLoad(getBitbucketStatus, 'bitbucket-status')} selection={selection} navigate={navigate} />
}
const open = (routes: Routes) => {
  navigated.mockClear()
  const api = stubApi({ [STATUS]: { body: statusConfigured() }, [REPOS]: { body: repositories() }, ...routes })
  render(<Page />)
  return api
}
const empty = (state: PullRequestList['state']): PullRequestList => ({ ...pullRequestsBeforeScan(), state, pull_requests: [] })

describe('pull request list', () => {
  test('lists the open pull requests of the first repository with branches, author and scan state', async () => {
    const api = open({ [list()]: { body: pullRequestsAfterHeadMoved() } })
    const rows = (await screen.findAllByRole('row')).slice(1)
    expect(rows).toHaveLength(2)

    const scanned = within(rows[0])
    expect(scanned.getByText('#7 Change 7')).toBeVisible()
    expect(scanned.getByText('Dev One')).toBeVisible()
    expect(scanned.getByText('feature/change-7')).toBeVisible()
    expect(scanned.getByText('1 scan')).toBeVisible()
    expect(scanned.getByText(/1 static finding · static risk 45\/100/)).toBeVisible()
    expect(rows[0].querySelector('[data-stale]')).toHaveAttribute('data-stale', 'stale')

    expect(within(rows[1]).getByText('Not scanned')).toBeVisible()
    expect(rows[1].querySelector('[data-stale]')).toBeNull()
    expect(api.count(list())).toBe(1)
  })

  test('each row links to Bitbucket in a new tab without leaking the opener', async () => {
    open({ [list()]: { body: pullRequestsBeforeScan() } })
    const link = await screen.findByRole('link', { name: /Open in Bitbucket.*pull request 7/ })
    expect(link).toHaveAttribute('href', 'https://bitbucket.org/acme/ledger/pull-requests/7')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  test('Analyze opens PR analysis for that pull request', async () => {
    open({ [list()]: { body: pullRequestsBeforeScan() } })
    await userEvent.click(await screen.findByRole('button', { name: /Analyze pull request 8/ }))
    expect(navigated).toHaveBeenLastCalledWith('pr-analysis', { slug: 'ledger', pullRequestId: '8' })
  })

  test('the state filter asks the API again and shows an empty state', async () => {
    const api = open({ [list()]: { body: pullRequestsBeforeScan() }, [list('merged')]: { body: empty('merged') } })
    await screen.findByText('#7 Change 7')
    await userEvent.click(screen.getByRole('button', { name: 'Merged' }))

    expect(await screen.findByRole('heading', { name: 'No merged pull requests' })).toBeVisible()
    expect(screen.queryByText('#7 Change 7')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Merged' })).toHaveAttribute('aria-pressed', 'true')
    expect(api.count(list('merged'))).toBe(1)
  })

  test('while another state loads, the previous list is not shown as the new one', async () => {
    const pending = deferred<{ body: unknown }>()
    open({ [list()]: { body: pullRequestsBeforeScan() }, [list('declined')]: () => pending.promise as never })
    await screen.findByText('#7 Change 7')
    await userEvent.click(screen.getByRole('button', { name: 'Declined' }))

    expect(await screen.findByText(/Loading declined pull requests/)).toBeVisible()
    expect(screen.queryByText('#7 Change 7')).not.toBeInTheDocument()
    pending.resolve({ body: empty('declined') })
    expect(await screen.findByRole('heading', { name: 'No declined pull requests' })).toBeVisible()
  })

  test('search narrows the returned list without another request, and can be cleared', async () => {
    const api = open({ [list()]: { body: pullRequestsBeforeScan() } })
    await screen.findByText('#7 Change 7')
    const box = screen.getByRole('searchbox', { name: 'Search pull requests' })

    await userEvent.type(box, 'change-8')
    expect(screen.queryByText('#7 Change 7')).not.toBeInTheDocument()
    expect(screen.getByText('#8 Change 8')).toBeVisible()
    expect(screen.getByText(/1 of 2/)).toBeVisible()

    await userEvent.clear(box)
    await userEvent.type(box, 'nothing like this')
    expect(screen.getByRole('heading', { name: /No pull request matches/ })).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'Clear search' }))
    expect(screen.getByText('#7 Change 7')).toBeVisible()
    expect(api.count(list())).toBe(1)
  })

  test('a truncated list says that only the first 200 are shown', async () => {
    open({ [list()]: { body: { ...pullRequestsBeforeScan(), truncated: true } } })
    expect(await screen.findByRole('heading', { name: /Only the first 200 open pull requests are shown/ })).toBeVisible()
  })

  test('choosing another repository loads its pull requests', async () => {
    const second = { ...repositories()[0], id: 'acme/billing', slug: 'billing', name: 'Billing' }
    const api = open({
      [REPOS]: { body: [...repositories(), second] },
      [list()]: { body: pullRequestsBeforeScan() },
      [list('open', 'billing')]: { body: { ...empty('open'), repository: second } },
    })
    await screen.findByText('#7 Change 7')
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Repository' }), 'billing')
    expect(await screen.findByRole('heading', { name: 'No open pull requests' })).toBeVisible()
    expect(api.count(list('open', 'billing'))).toBe(1)
  })

  test('Refresh asks Bitbucket again', async () => {
    const api = open({ [list()]: [{ body: pullRequestsBeforeScan() }, { body: pullRequestsAfterHeadMoved() }] })
    await screen.findByText('#7 Change 7')
    await userEvent.click(screen.getByRole('button', { name: /Refresh/ }))
    expect(await screen.findByText('1 scan')).toBeVisible()
    expect(api.count(list())).toBe(2)
  })
})

describe('pull request list: failures and setup', () => {
  test('a Bitbucket failure shows the message, the code and a working Retry', async () => {
    open({ [list()]: [error(503, 'bitbucket_unavailable', 'Bitbucket did not respond in time.'), { body: pullRequestsBeforeScan() }] })
    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText('Could not load the pull requests')).toBeVisible()
    expect(within(alert).getByText('Bitbucket did not respond in time.')).toBeVisible()
    expect(within(alert).getByText('bitbucket_unavailable')).toBeVisible()

    await userEvent.click(within(alert).getByRole('button', { name: /Retry/ }))
    expect(await screen.findByText('#7 Change 7')).toBeVisible()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  test('not configured: shows the setup message and requests nothing else', async () => {
    const api = open({ [STATUS]: { body: statusNotConfigured() } })
    expect(await screen.findByRole('heading', { name: 'Bitbucket is not configured' })).toBeVisible()
    expect([api.count(REPOS), api.count(list())]).toEqual([0, 0])
  })

  test('the server losing its settings mid-way still shows the setup message', async () => {
    open({ [list()]: { status: 503, body: notConfiguredError() } })
    expect(await screen.findByRole('heading', { name: 'Bitbucket is not configured' })).toBeVisible()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  test('no approved repository returned: points to the Repositories page', async () => {
    const api = open({ [REPOS]: { body: [] } })
    await userEvent.click(await screen.findByRole('button', { name: /Open Repositories/ }))
    expect(navigated).toHaveBeenLastCalledWith('repositories', undefined)
    expect(api.calls.some(call => call.includes('pull-requests'))).toBe(false)
  })
})
