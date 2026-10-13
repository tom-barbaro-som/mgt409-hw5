import { useCallback, useState } from 'react'
import { api } from './api'
import { Approvals } from './components/Approvals'
import { CashCard } from './components/CashCard'
import { HandsomeDan } from './components/HandsomeDan'
import { TicketList } from './components/TicketList'
import { TicketPanel } from './components/TicketPanel'
import { usePolling } from './hooks'
import type { ApprovalRequest, Cash, RunJob, TicketsResponse } from './types'

interface Toast { id: number; msg: string; tone: 'ok' | 'err' }

export default function App() {
  const [data, setData] = useState<TicketsResponse | null>(null)
  const [cash, setCash] = useState<Cash | null>(null)
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [activeJob, setActiveJob] = useState<RunJob | null>(null)
  const [starting, setStarting] = useState(false)
  const [offline, setOffline] = useState(false)
  const [toasts, setToasts] = useState<Toast[]>([])

  const notify = useCallback((msg: string, tone: 'ok' | 'err' = 'ok') => {
    const id = Date.now() + Math.random()
    setToasts((t) => [...t, { id, msg, tone }])
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 6000)
  }, [])

  const loadTickets = useCallback(async () => {
    try {
      const res = await api.tickets()
      setData(res)
      setOffline(false)
      setSelected((cur) => cur ?? res.tickets[0]?.id ?? null)
      // pick up a run that was already going (e.g. after a page reload)
      const running = res.tickets.find((t) => t.agent_run_in_progress)
      if (running && !activeJob) {
        setActiveJob({ run_id: running.agent_run_in_progress!, ticket_id: running.id, status: 'running', started_at: '', finished_at: null })
      }
    } catch {
      setOffline(true)
    }
  }, [activeJob])
  const loadCash = useCallback(async () => setCash(await api.cash()), [])
  const loadApprovals = useCallback(async () => setApprovals((await api.approvals()).requests), [])
  const refreshAll = useCallback(() => { loadTickets(); loadCash(); loadApprovals() }, [loadTickets, loadCash, loadApprovals])

  usePolling(loadTickets, 4000)
  usePolling(loadCash, 2000)
  usePolling(loadApprovals, 3000)

  // While a run is active, check on it; when it ends, the live view becomes the summary.
  usePolling(async () => {
    if (!activeJob) return
    const job = await api.run(activeJob.run_id)
    if (job.status !== 'running') {
      setActiveJob(null)
      refreshAll()
      notify(job.status === 'completed' ? `Ticket ${job.ticket_id}: agents finished.` : `Ticket ${job.ticket_id}: run ${job.status.replaceAll('_', ' ')}.`,
        job.status === 'completed' ? 'ok' : 'err')
    }
  }, 2000, !!activeJob)

  const startRun = async (ticketId: number) => {
    setStarting(true)
    try {
      setActiveJob(await api.runTicket(ticketId))
      loadTickets()
    } catch (e) {
      notify((e as Error).message, 'err')
    } finally {
      setStarting(false)
    }
  }

  const reset = async () => {
    if (!window.confirm('Reset the working database to the original data? All payments, drafts, and statuses will be undone.')) return
    try {
      await api.reset()
      notify('Working database reset to the original data.')
      refreshAll()
    } catch (e) {
      notify((e as Error).message, 'err')
    }
  }

  const ticket = data?.tickets.find((t) => t.id === selected) ?? null

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <HandsomeDan />
          <div>
            <h1>Campus Customs</h1>
            <div className="brand-sub">Operations Desk · New Haven{data ? ` · Desk date ${data.desk_date_today}` : ''}</div>
          </div>
        </div>
        <CashCard cash={cash} error={offline} />
      </header>

      {offline && (
        <div className="banner">Can't reach the backend at http://localhost:8000. Start it from <code>backend/</code> with <code>uvicorn main:app --reload --port 8000</code>.</div>
      )}

      <div className="layout">
        <nav className="tickets">
          <div className="section-head">
            <h3>Tickets</h3>
            {data && <span className="muted small">{data.open} open · {data.resolved} resolved</span>}
          </div>
          {data && <TicketList tickets={data.tickets} selected={selected} onSelect={setSelected} />}
        </nav>

        {ticket ? (
          <TicketPanel ticket={ticket} activeJob={activeJob} starting={starting} onRun={() => startRun(ticket.id)} />
        ) : (
          <main className="panel"><div className="empty big">Loading tickets…</div></main>
        )}

        <Approvals requests={approvals} cash={cash} onDecided={refreshAll} notify={notify} />
      </div>

      <footer className="footer">
        <span>Boola Boola · Handsome Dan keeps an eye on the desk. No messages or payments leave this system without you.</span>
        <button className="link" onClick={reset} disabled={!!activeJob}>Reset demo data</button>
      </footer>

      <div className="toasts">
        {toasts.map((t) => <div key={t.id} className={`toast ${t.tone}`}>{t.msg}</div>)}
      </div>
    </div>
  )
}
