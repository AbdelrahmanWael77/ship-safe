import { describe, expect, test, vi } from 'vitest'
import { ApiError, api, describeError, isApiError } from './api'

function respond(status: number, body: unknown, init: ResponseInit = {}) {
  const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
    new Response(typeof body === 'string' ? body : JSON.stringify(body), { status, ...init }))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const failure = async (run: Promise<unknown>) => run.then(() => { throw new Error('expected a rejection') }, error => error as ApiError)

describe('api()', () => {
  test('returns the parsed body and passes the request through unchanged', async () => {
    const fetchMock = respond(200, { status: 'ok' })
    const options = { method: 'POST', body: '{}' }
    expect(await api<{ status: string }>('/api/health', options)).toEqual({ status: 'ok' })
    expect(fetchMock).toHaveBeenCalledWith('/api/health', options)
  })

  test('a Bitbucket route error keeps its status, code and message', async () => {
    respond(503, { detail: 'Bitbucket is not configured. Set SHIPSAFE_BITBUCKET_WORKSPACE…', code: 'bitbucket_not_configured' })
    const error = await failure(api('/api/bitbucket/repositories'))
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toBeInstanceOf(Error)  // existing callers read `.message`
    expect([error.status, error.code]).toEqual([503, 'bitbucket_not_configured'])
    expect(error.message).toMatch(/^Bitbucket is not configured/)
  })

  test('a local route error has a message and no code', async () => {
    respond(404, { detail: 'Scan report not found' })
    const error = await failure(api('/api/scans/nope'))
    expect([error.status, error.code, error.message]).toEqual([404, null, 'Scan report not found'])
  })

  test('a request-validation error (422, detail is a list) becomes one readable message', async () => {
    respond(422, { detail: [{ loc: ['body', 'head_commit'], msg: "String should match pattern '^[0-9a-f]{40}$'", type: 'string_pattern_mismatch' }] })
    const error = await failure(api('/api/x', { method: 'POST' }))
    expect([error.status, error.code]).toEqual([422, null])
    expect(error.message).toBe("Invalid request: head_commit: String should match pattern '^[0-9a-f]{40}$'")
  })

  test('an error without a JSON body falls back to the status', async () => {
    respond(502, '<html>Bad gateway</html>', { statusText: '' })
    const error = await failure(api('/api/x'))
    expect([error.status, error.code, error.message]).toEqual([502, null, 'API error 502'])
  })

  test('a non-string code is ignored', async () => {
    respond(400, { detail: 'Nope', code: 42 })
    expect((await failure(api('/api/x'))).code).toBeNull()
  })

  test('an unreachable API is reported with status 0 and the start-the-backend hint', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch') }))
    const error = await failure(api('/api/demo'))
    expect([error.status, error.code]).toEqual([0, null])
    expect(error.message).toBe('Could not reach the API. Start FastAPI on port 8000, then refresh this page.')
  })
})

describe('isApiError()', () => {
  test('matches by code, or any ApiError when no code is given', () => {
    const error = new ApiError('The pull request has new commits', 409, 'head_changed')
    expect(isApiError(error)).toBe(true)
    expect(isApiError(error, 'head_changed')).toBe(true)
    expect(isApiError(error, 'diff_too_large')).toBe(false)
    expect(isApiError(new Error('plain'))).toBe(false)
    expect(isApiError('text', 'head_changed')).toBe(false)
  })
})

describe('describeError()', () => {
  test.each([
    ['a string', 'Repository not allowed', 403, 'Repository not allowed'],
    ['an empty string', '', 500, 'API error 500'],
    ['a list of plain values', ['first', 'second'], 422, 'Invalid request: first; second'],
    ['an empty list', [], 422, 'API error 422'],
    ['nothing', undefined, 418, 'API error 418'],
  ])('%s', (_name, detail, status, expected) => {
    expect(describeError(detail, status)).toBe(expected)
  })
})
