import type { ApprovalRequest, AgentEvent, Cash, RunJob, RunSummary, Ticket, TicketsResponse } from './types'

export const API_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

export class ApiError extends Error {}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    const detail = body?.detail
    const msg = typeof detail === 'string' ? detail : detail?.error ?? `Request failed (${res.status})`
    throw new ApiError(msg)
  }
  return body as T
}

const post = <T>(path: string, data?: unknown) =>
  call<T>(path, { method: 'POST', body: data === undefined ? undefined : JSON.stringify(data) })

export const api = {
  tickets: () => call<TicketsResponse>('/api/tickets'),
  ticket: (id: number) => call<Ticket>(`/api/tickets/${id}`),
  runTicket: (id: number) => post<RunJob>(`/api/tickets/${id}/run`),
  run: (runId: string) => call<RunJob>(`/api/runs/${runId}`),
  runSummary: (runId: string) => call<RunSummary>(`/api/runs/${runId}/summary`),
  events: (runId: string, after: number) =>
    call<{ last_seq: number; events: AgentEvent[] }>(
      `/api/events?run_id=${encodeURIComponent(runId)}&after=${after}&limit=500`,
    ),
  approvals: () => call<{ requests: ApprovalRequest[] }>('/api/approvals?status=pending'),
  approve: (id: number, approved_by: string) =>
    post<Record<string, any>>(`/api/approvals/${id}/approve`, { approved_by }),
  reject: (id: number, rejected_by: string, reason: string) =>
    post<Record<string, any>>(`/api/approvals/${id}/reject`, { rejected_by, reason }),
  cash: () => call<Cash>('/api/cash'),
  reset: () => post<Record<string, any>>('/api/reset', { confirm: true }),
}
