import type { Ticket } from './types'

/** One label + tone per ticket, shared by the list and the detail panel. */
export function statusOf(t: Ticket): { label: string; tone: string } {
  if (t.agent_run_in_progress) return { label: 'Agents working', tone: 'working' }
  if (t.is_resolved) return { label: 'Resolved', tone: 'resolved' }
  if (t.status === 'waiting_approval') return { label: 'Run complete · needs you', tone: 'waiting' }
  if (t.status === 'blocked') return { label: 'Blocked', tone: 'blocked' }
  return { label: 'Open', tone: 'open' }
}
