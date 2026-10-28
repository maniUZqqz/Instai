import { useCallback, useEffect, useRef, useState } from 'react'
import { api, errorText, ApiError } from './api/client'
import type { Job } from './api/types'
import { useToast } from './components/feedback'

export interface Query<T> {
  data: T | undefined
  error: ApiError | null
  /** true only while there is nothing to show yet */
  loading: boolean
  reload: () => void
  setData: (d: T | undefined | ((prev: T | undefined) => T | undefined)) => void
}

/** GET a path; optional polling (the next request starts only after the previous one ended). `path = null` disables it. */
export function useQuery<T>(path: string | null, opts: { interval?: number | ((d: T | undefined) => number | false) } = {}): Query<T> {
  const [state, setState] = useState<{ path: string | null; data: T | undefined; error: ApiError | null; loading: boolean }>({
    path,
    data: undefined,
    error: null,
    loading: path !== null,
  })
  const [tick, setTick] = useState(0)
  const intervalRef = useRef(opts.interval)
  intervalRef.current = opts.interval
  const dataRef = useRef<T | undefined>(undefined)

  useEffect(() => {
    if (path === null) {
      setState({ path, data: undefined, error: null, loading: false })
      return
    }
    let alive = true
    let timer: number | undefined
    const ctrl = new AbortController()
    setState((s) => (s.path === path ? s : { path, data: undefined, error: null, loading: true }))
    if (state.path !== path) dataRef.current = undefined
    const run = async () => {
      if (document.hidden && dataRef.current !== undefined) {
        timer = window.setTimeout(run, 2000)
        return
      }
      try {
        const d = await api.get<T>(path, ctrl.signal)
        if (!alive) return
        dataRef.current = d
        setState({ path, data: d, error: null, loading: false })
      } catch (e) {
        if (!alive || (e as Error).name === 'AbortError') return
        setState((s) => ({ ...s, path, error: e as ApiError, loading: false }))
      }
      if (!alive) return
      const iv = typeof intervalRef.current === 'function' ? intervalRef.current(dataRef.current) : intervalRef.current
      if (iv) timer = window.setTimeout(run, iv)
    }
    run()
    return () => {
      alive = false
      ctrl.abort()
      if (timer) window.clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, tick])

  const reload = useCallback(() => setTick((n) => n + 1), [])
  const setData = useCallback((d: T | undefined | ((prev: T | undefined) => T | undefined)) => {
    setState((s) => {
      const next = typeof d === 'function' ? (d as (p: T | undefined) => T | undefined)(s.data) : d
      dataRef.current = next
      return { ...s, data: next }
    })
  }, [])
  const same = state.path === path
  return { data: same ? state.data : undefined, error: same ? state.error : null, loading: path !== null && (!same || state.loading), reload, setData }
}

/** Run one async action with busy/error state; errors become Persian toasts. */
export function useAction() {
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const run = useCallback(
    async <T,>(fn: () => Promise<T>, o?: { success?: string; silent?: boolean }): Promise<T | undefined> => {
      setBusy(true)
      setError(null)
      try {
        const r = await fn()
        if (o?.success) toast.ok(o.success)
        return r
      } catch (e) {
        const m = errorText(e)
        setError(m)
        if (!o?.silent) toast.err(m)
        return undefined
      } finally {
        setBusy(false)
      }
    },
    [toast],
  )
  return { busy, error, run, clearError: () => setError(null) }
}

const TERMINAL = ['succeeded', 'failed', 'cancelled']
export const isTerminal = (j: Pick<Job, 'status'> | null | undefined) => !!j && TERMINAL.includes(j.status)

/** Poll one job every ~1.5 s until it is finished. */
export function useJobPoll(jobId: number | null, onDone?: (j: Job) => void, intervalMs = 1500) {
  const [job, setJob] = useState<Job | null>(null)
  const [offline, setOffline] = useState(false)
  const doneRef = useRef(onDone)
  doneRef.current = onDone
  useEffect(() => {
    if (jobId === null) {
      setJob(null)
      setOffline(false)
      return
    }
    let alive = true
    let timer: number | undefined
    let fails = 0
    const poll = async () => {
      try {
        const j = await api.get<Job>(`/jobs/${jobId}`)
        if (!alive) return
        fails = 0
        setOffline(false)
        setJob(j)
        if (isTerminal(j)) {
          doneRef.current?.(j)
          return
        }
      } catch {
        fails += 1
        if (alive && fails >= 3) setOffline(true)
      }
      if (alive) timer = window.setTimeout(poll, intervalMs)
    }
    poll()
    return () => {
      alive = false
      if (timer) window.clearTimeout(timer)
    }
  }, [jobId, intervalMs])
  return { job, offline }
}

/** Start a long operation that returns `{job}` and follow it to the end. `result` is `job.result` once it has succeeded. */
export function useJobRunner<R = Record<string, any>>(opts: { onSucceeded?: (j: Job) => void; onFinished?: (j: Job) => void } = {}) {
  const [jobId, setJobId] = useState<number | null>(null)
  const [seed, setSeed] = useState<Job | null>(null)
  const [starting, setStarting] = useState(false)
  const [startError, setStartError] = useState<string | null>(null)
  const toast = useToast()
  const optsRef = useRef(opts)
  optsRef.current = opts
  const { job: polled, offline } = useJobPoll(jobId, (j) => {
    optsRef.current.onFinished?.(j)
    if (j.status === 'succeeded') optsRef.current.onSucceeded?.(j)
  })
  const job = polled ?? seed
  const start = useCallback(
    async (fn: () => Promise<{ job?: Job | null } | undefined>) => {
      setStarting(true)
      setStartError(null)
      setSeed(null)
      try {
        const r = await fn()
        if (r?.job) {
          setSeed(r.job)
          setJobId(r.job.id)
        }
        return r
      } catch (e) {
        const m = errorText(e)
        setStartError(m)
        toast.err(m)
        return undefined
      } finally {
        setStarting(false)
      }
    },
    [toast],
  )
  const adopt = useCallback((id: number) => {
    setSeed(null)
    setJobId(id)
  }, [])
  const reset = useCallback(() => {
    setJobId(null)
    setSeed(null)
    setStartError(null)
  }, [])
  const running = jobId !== null && !isTerminal(job)
  return {
    job,
    jobId,
    busy: starting || running,
    starting,
    startError,
    start,
    adopt,
    reset,
    offline,
    succeeded: job?.status === 'succeeded',
    failed: job?.status === 'failed' || job?.status === 'cancelled',
    result: (job?.status === 'succeeded' ? job.result : null) as R | null,
  }
}

/** Remember a UI choice (tab, filter...) per browser. Never required: falls back silently when storage is blocked. */
export function useStored<T extends string>(key: string, initial: T): [T, (v: T) => void] {
  const [v, setV] = useState<T>(() => {
    try {
      return (localStorage.getItem('instai.' + key) as T | null) ?? initial
    } catch {
      return initial
    }
  })
  const set = useCallback(
    (nv: T) => {
      setV(nv)
      try {
        localStorage.setItem('instai.' + key, nv)
      } catch {
        /* ignore */
      }
    },
    [key],
  )
  return [v, set]
}

/** Keep the document title in sync with the page. */
export function useTitle(title: string | undefined) {
  useEffect(() => {
    document.title = title ? `${title} · InstAI` : 'InstAI'
  }, [title])
}

/** A tab kept in the URL hash (#arcs) so reload and the back button keep it. */
export function useHashTab<T extends string>(keys: readonly T[], def: T): [T, (k: T) => void] {
  const read = (): T => {
    const h = window.location.hash.slice(1)
    return (keys as readonly string[]).includes(h) ? (h as T) : def
  }
  const [tab, setTab] = useState<T>(read)
  useEffect(() => {
    const on = () => setTab(read())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  const set = useCallback((k: T) => {
    window.history.replaceState(window.history.state, '', `${window.location.pathname}${window.location.search}#${k}`)
    setTab(k)
  }, [])
  return [tab, set]
}
