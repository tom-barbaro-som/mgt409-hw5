import { useEffect, useState } from 'react'
import { agentMeta, agentName } from '../agents'
import { api } from '../api'
import type { RunSummary } from '../types'

const OUTCOME: Record<string, string> = {
  completed: 'Run complete',
  paused_for_budget_approval: 'Paused: AI budget reached (approve more in the queue)',
  error: 'Run failed',
  interrupted: 'Run interrupted',
  skipped: 'Skipped',
}

/** After a run: one brief card per agent that took part, replacing the live feed. */
export function RunSummaryView({ runId, refreshKey }: { runId: string; refreshKey: unknown }) {
  const [summary, setSummary] = useState<RunSummary | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.runSummary(runId).then(setSummary).catch((e) => setError(String(e.message ?? e)))
  }, [runId, refreshKey])

  if (error) return <p className="muted">Summary unavailable: {error}</p>
  if (!summary) return <p className="muted">Loading summary…</p>

  const path = summary.agents
  const chain = ['boss', ...summary.agents.flatMap((a) => a.delegated_to ?? [])]
    .filter((v, i, arr) => arr.indexOf(v) === i)
    .map((a) => agentName(a))
  const seconds = summary.started_at && summary.finished_at
    ? Math.round((Date.parse(summary.finished_at) - Date.parse(summary.started_at)) / 1000)
    : null

  return (
    <section className="summary">
      <div className="section-head">
        <h3>{OUTCOME[summary.status] ?? summary.status}</h3>
        <span className="muted small">
          {chain.join(' → ')}
          {summary.usage?.total_tokens ? ` · ${summary.usage.total_tokens.toLocaleString()} tokens` : ''}
          {seconds ? ` · ${seconds}s` : ''}
        </span>
      </div>
      {summary.decision && <p className="decision">{summary.decision}</p>}
      <div className="agent-cards">
        {path.map((a) => {
          const meta = agentMeta(a.agent)
          const askedBy: string[] = Array.isArray(a.delegated_by) ? a.delegated_by : a.delegated_by ? [a.delegated_by] : []
          return (
            <article key={a.agent} className="agent-card">
              <header>
                <span className="avatar" aria-hidden>{meta?.icon}</span>
                <div>
                  <div className="lane-name">{meta?.name}</div>
                  <div className="lane-state">
                    {askedBy.length ? `Asked by ${askedBy.map(agentName).join(' and ')}` : 'Owned the ticket'}
                    {a.delegated_to?.length ? ` · asked ${a.delegated_to.map(agentName).join(', ')}` : ''}
                  </div>
                </div>
              </header>
              {a.actions.length > 0 && (
                <ul className="actions">{a.actions.map((x, i) => <li key={i}>{x}</li>)}</ul>
              )}
              {a.checks.length > 0 && <div className="checks">{a.checks.map((c) => <span key={c} className="chip">{c}</span>)}</div>}
              {a.outcome && <p className="outcome">{a.outcome}</p>}
            </article>
          )
        })}
      </div>
    </section>
  )
}
