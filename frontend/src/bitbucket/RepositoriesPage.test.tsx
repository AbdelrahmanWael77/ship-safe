import { describe, expect, test } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { deferred, networkDown, stubApi } from '../test/api'
import type { Routes } from '../test/api'
import { notConfiguredError, repositories, statusConfigured, statusNotConfigured } from '../test/fixtures'
import type { BitbucketRepository } from '../types'
import { getBitbucketStatus } from './client'
import { RepositoriesPage } from './RepositoriesPage'
import { useLoad } from './useLoad'

const STATUS = '/api/bitbucket/status'
const REPOS = '/api/bitbucket/repositories'

// The page receives the status from the app; this wrapper loads it the same way.
function Page() {
  return <RepositoriesPage status={useLoad(getBitbucketStatus, 'bitbucket-status')} />
}
const open = (routes: Routes) => { const api = stubApi(routes); render(<Page />); return api }
const error = (status: number, code: string, detail: string) => ({ status, body: { detail, code } })

describe('connection status', () => {
  test('shows a checking state, then what the status route reported', async () => {
    const pending = deferred<{ body: unknown }>()
    open({ [STATUS]: () => pending.promise as never, [REPOS]: { body: repositories() } })
    expect(screen.getByText('Checking the Bitbucket configuration…')).toBeVisible()

    pending.resolve({ body: statusConfigured() })
    expect(await screen.findByText(/Bitbucket is configured/)).toBeVisible()
    expect(screen.getByText('acme')).toBeVisible()
    expect(screen.getByText(/1 approved repository\./)).toBeVisible()
    expect(screen.getByText(/never writes, merges or approves/)).toBeVisible()
  })

  test('not configured: explains the setup, names no secret value, and loads no repositories', async () => {
    const api = open({ [STATUS]: { body: statusNotConfigured() }, [REPOS]: error(503, 'bitbucket_not_configured', 'should not be requested') })
    expect(await screen.findByRole('heading', { name: 'Bitbucket is not configured' })).toBeVisible()
    for (const name of ['SHIPSAFE_BITBUCKET_WORKSPACE', 'SHIPSAFE_BITBUCKET_REPOSITORIES', 'SHIPSAFE_BITBUCKET_TOKEN']) {
      expect(screen.getByText(name)).toBeVisible()
    }
    expect(screen.getByText(/The token is a secret/)).toBeVisible()
    expect(screen.getByText(/local demo keeps working/)).toBeVisible()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(api.count(REPOS)).toBe(0)  // a call that is certain to fail is not made
  })

  test('not configured: "Check again" re-reads the status and then loads the repositories', async () => {
    const api = open({ [STATUS]: [{ body: statusNotConfigured() }, { body: statusConfigured() }], [REPOS]: { body: repositories() } })
    await userEvent.click(await screen.findByRole('button', { name: /Check again/ }))
    expect(await screen.findByRole('table')).toBeVisible()
    expect(screen.queryByText('Bitbucket is not configured')).not.toBeInTheDocument()
    expect([api.count(STATUS), api.count(REPOS)]).toEqual([2, 1])
  })

  test('the status request failing shows the error with Retry, and Retry recovers', async () => {
    const api = open({ [STATUS]: [networkDown, { body: statusConfigured() }], [REPOS]: { body: repositories() } })
    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText('Could not read the Bitbucket configuration')).toBeVisible()
    expect(within(alert).getByText(/Could not reach the API/)).toBeVisible()
    expect(api.count(REPOS)).toBe(0)

    await userEvent.click(within(alert).getByRole('button', { name: /Retry/ }))
    expect(await screen.findByRole('table')).toBeVisible()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  test('the server losing its settings after the status call still shows the setup message', async () => {
    open({ [STATUS]: { body: statusConfigured() }, [REPOS]: { status: 503, body: notConfiguredError() } })
    expect(await screen.findByRole('heading', { name: 'Bitbucket is not configured' })).toBeVisible()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('repository list', () => {
  test('shows a loading state, then exactly the repositories the API returned', async () => {
    const pending = deferred<{ body: unknown }>()
    open({ [STATUS]: { body: statusConfigured() }, [REPOS]: () => pending.promise as never })
    expect(await screen.findByText('Loading repositories from Bitbucket…')).toBeVisible()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()

    pending.resolve({ body: repositories() })
    const rows = within(await screen.findByRole('table')).getAllByRole('row').slice(1)
    expect(rows).toHaveLength(1)
    expect(within(rows[0]).getByText('Ledger')).toBeVisible()
    expect(within(rows[0]).getByText('acme/ledger')).toBeVisible()
    expect(within(rows[0]).getByText('main')).toBeVisible()
    expect(screen.getByText('1 repository')).toBeVisible()
    expect(screen.queryByText('Loading repositories from Bitbucket…')).not.toBeInTheDocument()
  })

  test('"Open in Bitbucket" uses the URL from the API and opens safely in a new tab', async () => {
    open({ [STATUS]: { body: statusConfigured() }, [REPOS]: { body: repositories() } })
    const link = await screen.findByRole('link', { name: /Open in Bitbucket/ })
    expect(link).toHaveAttribute('href', 'https://bitbucket.org/acme/ledger')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  test('a configured repository that Bitbucket did not return is never listed as a repository', async () => {
    const status = { ...statusConfigured(), repositories: ['ledger', 'billing-api'] }
    open({ [STATUS]: { body: status }, [REPOS]: { body: repositories() } })
    const table = await screen.findByRole('table')
    expect(within(table).queryByText(/billing-api/)).not.toBeInTheDocument()
    expect(within(table).getAllByRole('row')).toHaveLength(2)  // header + the one returned
    const note = screen.getByRole('note')
    expect(note).toHaveTextContent('One approved repository was not returned by Bitbucket: billing-api')
  })

  test('several repositories, and one without a default branch', async () => {
    const list: BitbucketRepository[] = [
      ...repositories(),
      { id: 'acme/billing-api', slug: 'billing-api', name: 'Billing API', url: 'https://bitbucket.org/acme/billing-api', default_branch: null },
    ]
    open({ [STATUS]: { body: { ...statusConfigured(), repositories: ['ledger', 'billing-api'] } }, [REPOS]: { body: list } })
    const rows = within(await screen.findByRole('table')).getAllByRole('row').slice(1)
    expect(rows.map(row => row.querySelector('strong')?.textContent)).toEqual(['Ledger', 'Billing API'])
    expect(within(rows[1]).getByText('Not reported')).toBeVisible()
    expect(screen.getByText('2 repositories')).toBeVisible()
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
  })

  test('empty: says so and explains what to check, without a table', async () => {
    open({ [STATUS]: { body: statusConfigured() }, [REPOS]: { body: [] } })
    expect(await screen.findByRole('heading', { name: 'Bitbucket returned no approved repositories' })).toBeVisible()
    expect(screen.getByText('SHIPSAFE_BITBUCKET_REPOSITORIES')).toBeVisible()
    expect(screen.getByText('0 repositories')).toBeVisible()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
  })

  test.each([
    [502, 'bitbucket_auth_failed', 'Bitbucket rejected the credentials', /cannot be fixed from the browser/],
    [503, 'bitbucket_unavailable', 'Bitbucket did not respond in time', /Wait a moment, then retry/],
    [502, 'bitbucket_error', 'Bitbucket returned an unexpected response', /check the API log/],
  ])('error %i %s: shows the API message, the next step and the code', async (status, code, detail, hint) => {
    open({ [STATUS]: { body: statusConfigured() }, [REPOS]: error(status, code, detail) })
    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText('Could not load the repositories')).toBeVisible()
    expect(within(alert).getByText(detail)).toBeVisible()
    expect(within(alert).getByText(hint)).toBeVisible()
    expect(within(alert).getByText(code)).toBeVisible()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.getByText(/Bitbucket is configured/)).toBeVisible()  // the status stays visible above the error
  })

  test('the API being unreachable shows the start-the-backend message and no error code', async () => {
    open({ [STATUS]: { body: statusConfigured() }, [REPOS]: networkDown })
    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText(/Could not reach the API/)).toBeVisible()
    expect(within(alert).queryByText(/Error code/)).not.toBeInTheDocument()
  })

  test('Retry after an error requests the list again and shows it', async () => {
    const api = open({ [STATUS]: { body: statusConfigured() }, [REPOS]: [error(503, 'bitbucket_unavailable', 'Bitbucket did not respond in time'), { body: repositories() }] })
    await userEvent.click(within(await screen.findByRole('alert')).getByRole('button', { name: /Retry/ }))
    expect(await screen.findByRole('table')).toBeVisible()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect([api.count(REPOS), api.count(STATUS)]).toEqual([2, 1])  // only the failed request is repeated
  })

  test('Retry that fails again keeps showing the error', async () => {
    const api = open({ [STATUS]: { body: statusConfigured() }, [REPOS]: error(503, 'bitbucket_unavailable', 'Bitbucket did not respond in time') })
    await userEvent.click(within(await screen.findByRole('alert')).getByRole('button', { name: /Retry/ }))
    await waitFor(() => expect(api.count(REPOS)).toBe(2))
    expect(await screen.findByRole('alert')).toBeVisible()
  })

  test('Refresh reloads the list and shows what Bitbucket returns now', async () => {
    const later: BitbucketRepository[] = [{ ...repositories()[0], name: 'Ledger (renamed)' }]
    const api = open({ [STATUS]: { body: statusConfigured() }, [REPOS]: [{ body: repositories() }, { body: later }] })
    await screen.findByText('Ledger')
    await userEvent.click(screen.getByRole('button', { name: /Refresh/ }))
    expect(await screen.findByText('Ledger (renamed)')).toBeVisible()
    expect(api.count(REPOS)).toBe(2)
  })

  test('only GET requests are made, and only to the ShipSafe API', async () => {
    const api = open({ [STATUS]: { body: statusConfigured() }, [REPOS]: { body: repositories() } })
    await screen.findByRole('table')
    expect(api.calls).toEqual([STATUS, REPOS])
  })
})
