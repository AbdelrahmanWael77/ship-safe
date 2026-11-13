// Calls to the read-only Bitbucket routes of the ShipSafe API. The browser
// never talks to Bitbucket and never holds a credential: the server does.
// Contract: docs/ARCHITECTURE.md, "Bitbucket routes".
import { api } from '../api'
import type { BitbucketRepository, BitbucketStatus } from '../types'

/** Whether the server has Bitbucket settings. Does not contact Bitbucket. */
export const getBitbucketStatus = () => api<BitbucketStatus>('/api/bitbucket/status')

/** The approved repositories, as Bitbucket currently returns them. */
export const listRepositories = () => api<BitbucketRepository[]>('/api/bitbucket/repositories')
