// Test helper: replaces `fetch` with a table of canned API answers.
// Nothing leaves jsdom; no test talks to the backend or to Bitbucket.
import { vi } from 'vitest'

export type Answer = { status?: number; body: unknown } | (() => { status?: number; body: unknown } | Promise<never>)
export type Routes = Record<string, Answer | Answer[]>

export interface StubbedApi {
  /** Request paths in the order they were made. */
  calls: string[]
  /** How many times one path was requested. */
  count: (path: string) => number
  /** Replace or add answers while a test runs. */
  set: (path: string, answer: Answer | Answer[]) => void
}

/**
 * `routes` maps "/api/…" (optionally prefixed with a method, "POST /api/…")
 * to an answer. A list of answers is served in order and the last repeats.
 * Unknown paths answer 404, like the real API.
 */
export function stubApi(routes: Routes): StubbedApi {
  const table: Routes = { ...routes }
  const served: Record<string, number> = {}
  const calls: string[] = []
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input)
    const method = (init?.method ?? 'GET').toUpperCase()
    calls.push(method === 'GET' ? path : `${method} ${path}`)
    const key = `${method} ${path}` in table ? `${method} ${path}` : path
    let answer = table[key]
    if (Array.isArray(answer)) {
      const index = Math.min(served[key] ?? 0, answer.length - 1)
      served[key] = (served[key] ?? 0) + 1
      answer = answer[index]
    }
    if (answer === undefined) return json(404, { detail: 'Not Found' })
    const resolved = typeof answer === 'function' ? await answer() : answer
    return json(resolved.status ?? 200, resolved.body)
  }))
  return {
    calls,
    count: path => calls.filter(call => call === path).length,
    set: (path, answer) => { table[path] = answer; delete served[path] },
  }
}

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

/** An answer that fails like a network outage (fetch itself rejects). */
export const networkDown: Answer = () => Promise.reject(new TypeError('Failed to fetch'))

/** A promise the test resolves by hand, to observe loading states. */
export function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}
