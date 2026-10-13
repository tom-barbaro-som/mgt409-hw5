import { useEffect, useMemo, useRef, useState } from 'react'
import { AGENTS, agentName } from '../agents'
import { api } from '../api'
import { usePolling } from '../hooks'
import type { AgentEvent } from '../types'

type LaneState = 'idle' | 'working' | 'waiting' | 'done'

const STATE_LABEL: Record<LaneState, string> = {
  idle: 'Not involved yet',
  working: 'Working',
  waiting: 'Waiting on teammate',
  done: 'Done',
}

/** Live view while a run is in progress: one lane per agent plus a feed of major steps only. */
export function LiveAgents({ runId }: { runId: string }) {
  const [events, setEvents] = useState<AgentEvent[]>([])
  const lastSeq = useRef(0)
  const feedRef = useRef<HTMLOListElement>(null)

  usePolling(async () => {
    const res = await api.events(runId, lastSeq.current)
    if (res.events.length) {
      lastSeq.current = res.events[res.events.length - 1].seq
      setEvents((prev) => [...prev, ...res.events])
    }
  }, 1200)

  const lanes = useMemo(() => {
    const state = new Map<string, { state: LaneState; line: string; waitingOn?: string }>()
    for (const e of events) {
      const who = e.agent
      if (!who || who === 'system') continue
      const cur = state.get(who) ?? { state: 'idle' as LaneState, line: '' }
      if (e.event === 'agent_started') cur.state = 'working'
      if (e.event === 'delegation') {
        cur.state = 'waiting'
        cur.waitingOn = e.detail.to_agent
      }
      if (e.event === 'agent_finished') cur.state = 'done'
      if (e.event !== 'agent_started') cur.line = e.summary
      state.set(who, cur)
      // a finished delegate hands control back to whoever asked
      if (e.event === 'agent_finished') {
        for (const [, other] of state) if (other.state === 'waiting' && other.waitingOn === who) other.state = 'working'
      }
    }
    return state
  }, [events])

  const feed = events.filter((e) => e.importance === 'major' && e.event !== 'ticket_run_started')

  useEffect(() => {
    feedRef.current?.lastElementChild?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [feed.length])

  return (
    <section className="live">
      <div className="section-head">
        <h3><span className="live-dot" /> Live: agents at work</h3>
        <span className="muted small">Updates every second · major steps only</span>
      </div>
      <div className="lanes">
        {AGENTS.map((a) => {
          const lane = lanes.get(a.id) ?? { state: 'idle' as LaneState, line: '' }
          return (
            <div key={a.id} className={`lane ${lane.state}`}>
              <div className="lane-head">
                <span className="avatar" aria-hidden>{a.icon}</span>
                <div>
                  <div className="lane-name">{a.name}</div>
                  <div className="lane-state">
                    {lane.state === 'waiting' && lane.waitingOn ? `Waiting on ${agentName(lane.waitingOn)}` : STATE_LABEL[lane.state]}
                  </div>
                </div>
              </div>
              <div className="lane-line">{lane.line || '—'}</div>
            </div>
          )
        })}
      </div>
      <ol className="feed" ref={feedRef}>
        {feed.length === 0 && <li className="muted">Handsome Dan is reading the ticket…</li>}
        {feed.map((e) => (
          <li key={e.seq} className={`feed-item ev-${e.event}`}>
            <span className="feed-time">{new Date(e.ts).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', second: '2-digit' })}</span>
            <span className="feed-agent">{agentName(e.agent)}</span>
            <span className="feed-text">{e.summary}</span>
          </li>
        ))}
      </ol>
    </section>
  )
}
