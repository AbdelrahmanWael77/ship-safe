import type { AIProvider, BitbucketStatus, Report } from '../types'
import type { BitbucketNavigate, BitbucketPage, BitbucketSelection } from './pages'
import { bitbucketPageLabel } from './pages'
import { PrAnalysisPage } from './PrAnalysisPage'
import { PullRequestsPage } from './PullRequestsPage'
import { RepositoriesPage } from './RepositoriesPage'
import type { Loaded } from './useLoad'

const DESCRIPTIONS: Record<BitbucketPage, string> = {
  repositories: 'Approved Bitbucket Cloud repositories, read-only. ShipSafe never writes to Bitbucket.',
  'pull-requests': 'Pull requests of an approved repository, read-only. Pick one to analyze it.',
  'pr-analysis': 'Scan a pull request at its exact commits, optionally followed by an AI review. Findings are suspicions; no code is run and nothing is written to Bitbucket.',
}

/** The Bitbucket part of the dashboard: heading plus the current Bitbucket page. */
export function BitbucketSection({ page, status, selection, navigate, onScanned, onOpenReport, providers = null, onShown, onReviewed }: {
  page: BitbucketPage
  status: Loaded<BitbucketStatus>
  selection: BitbucketSelection
  navigate: BitbucketNavigate
  onScanned: () => void
  onOpenReport: (id: string, page?: 'findings' | 'tests') => void
  onShown?: (report: Report) => void
  onReviewed?: (scanId: string) => void
  providers?: AIProvider[] | null
}) {
  return (
    <section aria-label="Bitbucket">
      <div className="subpage-heading">
        <div className="eyebrow"><span className="eyebrow-line" /> BITBUCKET / {bitbucketPageLabel(page)?.toUpperCase()}</div>
        <div className="subpage-title"><div><h1>{bitbucketPageLabel(page)}<span className="title-dot">.</span></h1><p>{DESCRIPTIONS[page]}</p></div></div>
      </div>
      {page === 'repositories' && <RepositoriesPage status={status} />}
      {page === 'pull-requests' && <PullRequestsPage status={status} selection={selection} navigate={navigate} />}
      {page === 'pr-analysis' && <PrAnalysisPage status={status} selection={selection} navigate={navigate} onScanned={onScanned} onOpenReport={onOpenReport} providers={providers} onShown={onShown} onReviewed={onReviewed} />}
    </section>
  )
}
