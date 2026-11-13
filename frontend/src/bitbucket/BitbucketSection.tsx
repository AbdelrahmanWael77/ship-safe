import type { BitbucketStatus } from '../types'
import type { BitbucketPage } from './pages'
import { bitbucketPageLabel } from './pages'
import { RepositoriesPage } from './RepositoriesPage'
import type { Loaded } from './useLoad'

const DESCRIPTIONS: Record<BitbucketPage, string> = {
  repositories: 'Approved Bitbucket Cloud repositories, read-only. ShipSafe never writes to Bitbucket.',
}

/** The Bitbucket part of the dashboard: heading plus the current Bitbucket page. */
export function BitbucketSection({ page, status }: { page: BitbucketPage; status: Loaded<BitbucketStatus> }) {
  return (
    <section aria-label="Bitbucket">
      <div className="subpage-heading">
        <div className="eyebrow"><span className="eyebrow-line" /> BITBUCKET / {page.toUpperCase()}</div>
        <div className="subpage-title"><div><h1>{bitbucketPageLabel(page)}<span className="title-dot">.</span></h1><p>{DESCRIPTIONS[page]}</p></div></div>
      </div>
      {page === 'repositories' && <RepositoriesPage status={status} />}
    </section>
  )
}
