import { FolderGit2 } from 'lucide-react'

/** Pages of the Bitbucket section. App.tsx adds these ids to its own page ids. */
export type BitbucketPage = 'repositories'

export const BITBUCKET_NAV: { id: BitbucketPage; label: string; icon: typeof FolderGit2 }[] = [
  { id: 'repositories', label: 'Repositories', icon: FolderGit2 },
]

export const isBitbucketPage = (page: string): page is BitbucketPage => BITBUCKET_NAV.some(item => item.id === page)

export const bitbucketPageLabel = (page: string) => BITBUCKET_NAV.find(item => item.id === page)?.label
