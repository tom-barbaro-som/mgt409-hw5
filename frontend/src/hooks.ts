import { useEffect, useRef } from 'react'

/** Calls `fn` now and every `ms` while `enabled`; the latest `fn` is always used. */
export function usePolling(fn: () => void | Promise<void>, ms: number, enabled = true) {
  const saved = useRef(fn)
  useEffect(() => {
    saved.current = fn
  })
  useEffect(() => {
    if (!enabled) return
    let stopped = false
    const tick = async () => {
      try {
        await saved.current()
      } catch {
        /* errors are surfaced by the caller's own state */
      }
      if (!stopped) timer = window.setTimeout(tick, ms)
    }
    let timer = window.setTimeout(tick, 0)
    return () => {
      stopped = true
      window.clearTimeout(timer)
    }
  }, [ms, enabled])
}

export const money = (n: number | null | undefined) =>
  n == null ? '—' : n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })
