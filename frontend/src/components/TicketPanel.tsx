import { LiveAgents } from './LiveAgents'
import { RunSummaryView } from './RunSummaryView'
import { statusOf } from '../status'
import type { RunJob, Ticket } from '../types'

export function TicketPanel({ ticket, activeJob, starting, onRun }: {
  ticket: Ticket
  activeJob: RunJob | null
  starting: boolean
  onRun: () => void
}) {
  const s = statusOf(ticket)
  const runningHere = activeJob?.ticket_id === ticket.id ? activeJob.run_id : ticket.agent_run_in_progress
  const busyElsewhere = !!activeJob && activeJob.ticket_id !== ticket.id
  const lastRun = ticket.last_run && ticket.last_run.status !== 'running' ? ticket.last_run : null
  const pending = ticket.approval_requests.filter((a) => a.status === 'pending').length

  const item = ticket.sku ? `${ticket.qty} × ${ticket.sku} · size ${ticket.size}` : null
  const link = ticket.invoice_id ? `Invoice ${ticket.invoice_id}` : ticket.lease_id ? `Lease ${ticket.lease_id}` : null

  return (
    <main className="panel">
      <div className="panel-head">
        <div>
          <div className="eyebrow">Ticket #{ticket.id} · {ticket.requester}</div>
          <h2>{ticket.subject}</h2>
        </div>
        <span className={`pill big ${s.tone}`}>{s.tone === 'resolved' ? '✓ ' : ''}{s.label}</span>
      </div>

      <dl className="facts">
        {item && <><dt>Item</dt><dd>{item}</dd></>}
        {link && <><dt>Linked</dt><dd>{link}</dd></>}
        <dt>Request</dt><dd>{(ticket.notes ?? '').split('\n')[0]}</dd>
        <dt>Status</dt><dd>{ticket.explanation}</dd>
      </dl>

      {!runningHere && (
        <div className="run-bar">
          <button className="btn primary" disabled={busyElsewhere || starting || ticket.is_resolved} onClick={onRun}>
            {starting ? 'Starting…' : lastRun ? 'Run agents again' : 'Start agent work'}
          </button>
          <span className="muted small">
            {ticket.is_resolved
              ? 'Resolved; reset the demo data to run it again.'
              : busyElsewhere
                ? `Agents are busy on ticket #${activeJob!.ticket_id}; one run at a time.`
                : pending
                  ? `${pending} request(s) from the last run await you on the right.`
                  : 'The Boss reads the ticket and brings in one or two teammates.'}
          </span>
        </div>
      )}

      {runningHere ? (
        <LiveAgents key={runningHere} runId={runningHere} />
      ) : lastRun ? (
        <RunSummaryView runId={lastRun.run_id} refreshKey={`${lastRun.finished_at}-${ticket.status}`} />
      ) : (
        <div className="empty big">
          <p>No agent has worked this ticket yet.</p>
          <p className="muted small">When you start, each agent's thinking and actions appear here live, then fold into a short summary.</p>
        </div>
      )}
    </main>
  )
}
