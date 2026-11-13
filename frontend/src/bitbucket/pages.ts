import { FolderGit2, GitPullRequest } from 'lucide-react'
import type { PullRequestState } from '../types'

/** Pages of the Bitbucket section. App.tsx adds these ids to its own page ids. */
export type BitbucketPage = 'repositories' | 'pull-requests' | 'pr-analysis'

/** Sidebar entries. PR analysis is reached from the pull request list, not from the sidebar. */
export const BITBUCKET_NAV: { id: BitbucketPage; label: string; icon: typeof FolderGit2 }[] = [
  { id: 'repositories', label: 'Repositories', icon: FolderGit2 },
  { id: 'pull-requests', label: 'Pull requests', icon: GitPullRequest },
]

const LABELS: Record<BitbucketPage, string> = {
  repositories: 'Repositories',
  'pull-requests': 'Pull requests',
  'pr-analysis': 'PR analysis',
}

export const isBitbucketPage = (page: string): page is BitbucketPage => page in LABELS

export const bitbucketPageLabel = (page: string) => (isBitbucketPage(page) ? LABELS[page] : undefined)

/** The sidebar entry that is highlighted for a page (PR analysis belongs to Pull requests). */
export const bitbucketNavEntry = (page: string) => (page === 'pr-analysis' ? 'pull-requests' : page)

/**
 * What the person picked in the Bitbucket section. Held by App so it survives
 * leaving the section and coming back.
 */
export interface BitbucketSelection {
  /** Repository slug, or null to use the first repository Bitbucket returns. */
  slug: string | null
  /** Which pull requests the list shows. */
  state: PullRequestState
  /** The pull request open in PR analysis. */
  pullRequestId: string | null
}

export const INITIAL_SELECTION: BitbucketSelection = { slug: null, state: 'open', pullRequestId: null }

/** Move within the section, optionally changing the selection. */
export type BitbucketNavigate = (page: BitbucketPage, change?: Partial<BitbucketSelection>) => void
