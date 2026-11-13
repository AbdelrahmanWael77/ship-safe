// The one place that talks to the ShipSafe API. Moved out of App.tsx
// unchanged in behaviour; the only addition is `ApiError`, which keeps the
// HTTP status and the API's error `code` so a screen can react to a specific
// failure (for example 503 `bitbucket_not_configured`) instead of only
// showing a message.
//
// Never put a credential here or in a VITE_* variable: everything in this
// bundle is readable in the browser. The Bitbucket token lives on the server.

/** Base URL of the API; empty in development, where Vite proxies /api. */
export const API_BASE = import.meta.env.VITE_API_BASE || ''
/** The scan list as the dashboard asks for it: the newest 100 scans (the API's maximum; its default is 12). */
export const SCAN_LIST_PATH = '/api/scans?limit=100'
/** How many scans SCAN_LIST_PATH can return at most. */
export const SCAN_LIST_LIMIT = 100
const API = API_BASE

export class ApiError extends Error {
  /** HTTP status, or 0 when the API could not be reached at all. */
  readonly status: number
  /** The API's machine-readable `code` (Bitbucket routes only), else null. */
  readonly code: string | null

  constructor(message: string, status: number, code: string | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

// FastAPI returns `detail` as a string for handled errors and as a list of
// {loc, msg} objects for request-validation (422) errors.
export function describeError(detail: unknown, status: number): string {
  if (typeof detail === 'string' && detail) return detail
  if (Array.isArray(detail)) {
    const parts = detail.map(item => {
      if (item && typeof item === 'object' && 'msg' in item) {
        const loc = Array.isArray((item as { loc?: unknown }).loc) ? ((item as { loc: unknown[] }).loc).filter(part => part !== 'body').join('.') : ''
        return loc ? `${loc}: ${String((item as { msg: unknown }).msg)}` : String((item as { msg: unknown }).msg)
      }
      return String(item)
    })
    if (parts.length) return `Invalid request: ${parts.join('; ')}`
  }
  return `API error ${status}`
}

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(API + path, options)
  } catch {
    throw new ApiError('Could not reach the API. Start FastAPI on port 8000, then refresh this page.', 0)
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({ detail: response.statusText }))
    const code = data && typeof data.code === 'string' && data.code ? data.code : null
    throw new ApiError(describeError(data?.detail, response.status), response.status, code)
  }
  return response.json() as Promise<T>
}

/** True for the API error with this `code`, e.g. `isApiError(error, 'head_changed')`. */
export function isApiError(error: unknown, code?: string): error is ApiError {
  return error instanceof ApiError && (code === undefined || error.code === code)
}
