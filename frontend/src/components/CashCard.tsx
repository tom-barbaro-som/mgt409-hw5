import { useEffect, useRef, useState } from 'react'
import { money } from '../hooks'
import type { Cash } from '../types'

/** Live checking balance; flashes and shows the change whenever money actually moves. */
export function CashCard({ cash, error }: { cash: Cash | null; error: boolean }) {
  const prev = useRef<number | null>(null)
  const [delta, setDelta] = useState<number | null>(null)

  useEffect(() => {
    if (!cash) return
    if (prev.current !== null && cash.balance !== prev.current) {
      setDelta(cash.balance - prev.current)
      const t = window.setTimeout(() => setDelta(null), 6000)
      prev.current = cash.balance
      return () => window.clearTimeout(t)
    }
    prev.current = cash.balance
  }, [cash])

  return (
    <div className={`cash-card ${delta !== null ? (delta < 0 ? 'flash-out' : 'flash-in') : ''}`} aria-live="polite">
      <div className="cash-label">
        <span className={`live-dot ${error ? 'off' : ''}`} /> Checking · live
      </div>
      <div className="cash-balance">{cash ? money(cash.balance) : '—'}</div>
      {delta !== null && <div className="cash-delta">{delta < 0 ? '−' : '+'}{money(Math.abs(delta))} just now</div>}
      {cash && delta === null && (
        <div className="cash-sub">
          {cash.pending_cash_requests_total > 0
            ? <>{money(cash.pending_cash_requests_total)} awaiting you · {money(cash.balance_after_all_pending)} if all approved</>
            : <>No payments awaiting approval</>}
        </div>
      )}
    </div>
  )
}
