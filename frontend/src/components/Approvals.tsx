import { useEffect, useState } from 'react'
import { agentName } from '../agents'
import { api } from '../api'
import { money } from '../hooks'
import type { ApprovalRequest, Cash } from '../types'

const MONEY_KINDS = new Set(['payment', 'purchase_order'])

function title(r: ApprovalRequest): string {
  const p = r.payload
  switch (r.kind) {
    case 'payment':
      return p.payment_kind === 'rent' ? `Pay rent to ${p.payee}` : `Pay invoice ${r.ref_id} to ${p.payee}`
    case 'purchase_order':
      return `Order ${p.qty} × ${p.product_name ?? p.sku} (${p.size}) from ${p.vendor_name}`
    case 'price_override':
      return `Discount ${p.sku} to ${money(p.unit_price)} each (${p.discount_pct}% off)`
    case 'message':
      return `Draft to ${p.recipient}: “${p.subject}”`
    case 'budget_extension':
      return `Allow ${Number(p.tokens_requested).toLocaleString()} more AI tokens`
  }
}

function Detail({ r, cash }: { r: ApprovalRequest; cash: Cash | null }) {
  const p = r.payload
  if (MONEY_KINDS.has(r.kind) && r.amount != null) {
    const after = cash ? cash.balance - r.amount : null
    const blocking = r.kind === 'purchase_order' ? r.blocking_invoices ?? [] : []
    return (
      <div className="impact">
        <div>
          Checking {money(cash?.balance)} → <strong className={after !== null && after < 0 ? 'neg' : ''}>{money(after)}</strong>
        </div>
        {after !== null && after < 0 && <div className="warn">Not enough cash; this approval will be refused.</div>}
        {blocking.map((inv) => (
          <div key={inv.id} className="warn">
            Vendor won't ship until invoice {inv.id} ({money(inv.amount)}) is paid.{' '}
            {inv.payment_request_id
              ? <>Approve payment request #{inv.payment_request_id} first.</>
              : <>No payment request for it yet. Run the agents on its ticket so Accounting files one.</>}
          </div>
        ))}
        {r.kind === 'payment' && p.due_date && <div className="muted small">Due {p.due_date}</div>}
        {r.kind === 'purchase_order' && <div className="muted small">Est. arrival {p.lead_days} days after approval</div>}
      </div>
    )
  }
  if (r.kind === 'price_override') {
    return (
      <div className="impact small">
        {p.qty} units: {money(p.total_price)} vs {money(p.total_at_list)} at list · margin {p.margin_pct}% · no cash moves
      </div>
    )
  }
  if (r.kind === 'message') {
    return (
      <details className="draft">
        <summary>Read draft · it will <strong>not</strong> be sent</summary>
        <pre>{p.body}</pre>
      </details>
    )
  }
  return null
}

export function Approvals({ requests, cash, onDecided, notify }: {
  requests: ApprovalRequest[]
  cash: Cash | null
  onDecided: () => void
  notify: (msg: string, tone?: 'ok' | 'err') => void
}) {
  const [approver, setApprover] = useState(() => localStorage.getItem('approver') ?? '')
  const [confirming, setConfirming] = useState<number | null>(null)
  const [rejecting, setRejecting] = useState<number | null>(null)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState<number | null>(null)

  useEffect(() => localStorage.setItem('approver', approver), [approver])

  const decide = async (r: ApprovalRequest, action: 'approve' | 'reject') => {
    if (!approver.trim()) return notify('Enter your name first, so the decision is signed.', 'err')
    setBusy(r.id)
    try {
      const res = action === 'approve' ? await api.approve(r.id, approver.trim()) : await api.reject(r.id, approver.trim(), reason.trim())
      const paid = res.payment ? ` Paid ${money(res.payment.amount)}; checking now ${money(res.payment.new_balance)}.` : ''
      notify(`#${r.id} ${action === 'approve' ? 'approved' : 'rejected'}.${paid}${res.ticket_resolved ? ` Ticket ${r.ticket_id} resolved.` : ''}`)
      setConfirming(null)
      setRejecting(null)
      setReason('')
    } catch (e) {
      notify(`#${r.id}: ${(e as Error).message}`, 'err')
      setConfirming(null)
    } finally {
      setBusy(null)
      onDecided()
    }
  }

  return (
    <aside className="approvals">
      <div className="section-head">
        <h3>Needs your OK {requests.length > 0 && <span className="count">{requests.length}</span>}</h3>
      </div>
      <label className="approver">
        Approving as
        <input value={approver} onChange={(e) => setApprover(e.target.value)} placeholder="Your name" />
      </label>
      <p className="muted small">Agents only draft. Nothing is paid, ordered, or discounted until you approve, and messages are never sent.</p>
      {requests.length === 0 && <div className="empty">Nothing waiting. 🐾</div>}
      <ul className="approval-list">
        {requests.map((r) => {
          const isMoney = MONEY_KINDS.has(r.kind)
          return (
            <li key={r.id} className={`approval ${isMoney ? 'money' : ''}`}>
              <div className="approval-top">
                <span className="kind">{r.kind.replace('_', ' ')}</span>
                <span className="muted small">#{r.id} · ticket {r.ticket_id ?? '—'} · {agentName(r.requested_by)}</span>
              </div>
              <div className="approval-title">
                {title(r)}
                {isMoney && r.amount != null && <span className="amount">{money(r.amount)}</span>}
              </div>
              <Detail r={r} cash={cash} />
              <p className="reason">{r.reason}</p>

              {confirming === r.id ? (
                <div className="confirm">
                  <span>Send {money(r.amount)} from checking now?</span>
                  <button className="btn approve" disabled={busy === r.id} onClick={() => decide(r, 'approve')}>Yes, pay</button>
                  <button className="btn ghost" onClick={() => setConfirming(null)}>Cancel</button>
                </div>
              ) : rejecting === r.id ? (
                <div className="confirm">
                  <input autoFocus value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason (agents will read it)" />
                  <button className="btn reject" disabled={busy === r.id || !reason.trim()} onClick={() => decide(r, 'reject')}>Reject</button>
                  <button className="btn ghost" onClick={() => setRejecting(null)}>Cancel</button>
                </div>
              ) : (
                <div className="buttons">
                  <button
                    className="btn approve"
                    disabled={busy === r.id}
                    onClick={() => (isMoney ? setConfirming(r.id) : decide(r, 'approve'))}
                  >
                    {r.kind === 'message' ? 'Approve draft' : isMoney ? 'Approve payment…' : 'Approve'}
                  </button>
                  <button className="btn ghost" onClick={() => { setRejecting(r.id); setReason('') }}>Reject</button>
                </div>
              )}
            </li>
          )
        })}
      </ul>
    </aside>
  )
}
