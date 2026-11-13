import { useCallback, useEffect, useRef, useState } from 'react'

export interface Loaded<T> {
  data: T | null
  error: Error | null
  loading: boolean
  /** Run the request again (used by Retry buttons). */
  reload: () => void
}

/**
 * Run `load` when `enabled` and whenever `key` changes, tracking loading and
 * error state. A response that arrives after a newer request started, or
 * after the component unmounted, is dropped.
 */
export function useLoad<T>(load: () => Promise<T>, key: string, enabled = true): Loaded<T> {
  const [state, setState] = useState<{ data: T | null; error: Error | null; loading: boolean }>({ data: null, error: null, loading: enabled })
  const [attempt, setAttempt] = useState(0)
  const latest = useRef(load)
  latest.current = load

  useEffect(() => {
    if (!enabled) {
      setState({ data: null, error: null, loading: false })
      return
    }
    let cancelled = false
    setState(previous => ({ data: previous.data, error: null, loading: true }))
    latest.current().then(
      data => { if (!cancelled) setState({ data, error: null, loading: false }) },
      error => { if (!cancelled) setState({ data: null, error: error instanceof Error ? error : new Error(String(error)), loading: false }) },
    )
    return () => { cancelled = true }
  }, [key, enabled, attempt])

  const reload = useCallback(() => setAttempt(value => value + 1), [])
  return { ...state, reload }
}
