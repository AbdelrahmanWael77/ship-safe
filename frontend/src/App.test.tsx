// Smoke test of the existing demo dashboard. It guards the behaviour that
// existed before the Bitbucket screens: the overview loads the latest stored
// scan and the sidebar switches pages. `fetch` is stubbed; nothing leaves jsdom.
import { expect, test, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from './App'
import report from '../../docs/example-scan-report.json'

const demo = {
  repository_path: '/demo/ledgerlite', name: 'LedgerLite (synthetic)', base_ref: 'main',
  default_head: 'feature/release-candidate', branches: [], note: 'Synthetic demo repository',
}
const history = [{
  id: report.id, created_at: report.created_at, repo_name: report.repo_name, base_ref: report.base_ref,
  head_ref: report.head_ref, duration_ms: report.duration_ms, summary: report.summary,
}]

function stubApi() {
  const calls: string[] = []
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    calls.push(url)
    const body = url.endsWith('/api/demo') ? demo
      : url.endsWith('/api/scans') ? history
      : url.endsWith('/ai/reviews') ? []
      : url.endsWith(`/api/scans/${report.id}`) ? report
      : null
    if (body === null) return new Response(JSON.stringify({ detail: 'Not Found' }), { status: 404 })
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  }))
  return calls
}

const nav = () => within(screen.getByRole('navigation', { name: 'Primary navigation' }))

test('the demo overview loads the latest stored scan', async () => {
  const calls = stubApi()
  render(<App />)

  expect(await screen.findByRole('heading', { name: 'Release overview' })).toBeInTheDocument()
  expect(screen.getByText('LOCAL DEMO')).toBeVisible()
  expect(screen.getByText(report.base_sha)).toBeVisible()
  expect(screen.getByText(report.head_sha)).toBeVisible()
  expect(screen.getByText('Requires engineering review')).toBeVisible()  // finding_count > 0
  expect(screen.getByText(report.summary.recommendation)).toBeVisible()
  expect(calls).toEqual(expect.arrayContaining(['/api/demo', '/api/scans', `/api/scans/${report.id}`]))
})

test('the sidebar switches between the existing pages', async () => {
  stubApi()
  const user = userEvent.setup()
  render(<App />)
  await screen.findByRole('heading', { name: 'Release overview' })

  await user.click(nav().getByRole('button', { name: /Risk findings/ }))
  for (const finding of report.findings) expect(await screen.findByText(finding.title)).toBeInTheDocument()

  await user.click(nav().getByRole('button', { name: /Scan history/ }))
  expect(await screen.findByRole('heading', { name: 'Recent analyses' })).toBeInTheDocument()
  expect(screen.getByText('1 saved')).toBeVisible()

  await user.click(nav().getByRole('button', { name: /Overview/ }))
  expect(await screen.findByRole('heading', { name: 'Release overview' })).toBeInTheDocument()
})
