export type AgentName = 'boss' | 'inventory' | 'accounting' | 'facilities' | 'customer_service'

export interface ApprovalRequest {
  id: number
  kind: 'payment' | 'purchase_order' | 'price_override' | 'message' | 'budget_extension'
  ticket_id: number | null
  ref_id: number | null
  amount: number | null
  payload: Record<string, any>
  reason: string
  requested_by: string
  status: 'pending' | 'approved' | 'approved_not_sent' | 'rejected'
  business_date: string
  created_at: string
  decided_by: string | null
  decision_note: string | null
  blocking_invoices?: { id: number; amount: number; due_date: string; payment_request_id: number | null }[]
}

export interface RunRef {
  run_id: string
  status: string
  started_at: string
  finished_at: string | null
}

export interface Ticket {
  id: number
  type: string
  requester: string
  subject: string
  sku: string | null
  size: string | null
  qty: number | null
  lease_id: number | null
  invoice_id: number | null
  status: 'open' | 'in_progress' | 'waiting_approval' | 'blocked' | 'resolved'
  notes: string | null
  created_at: string
  is_resolved: boolean
  explanation: string
  approval_requests: ApprovalRequest[]
  agent_run_in_progress: string | null
  last_run: RunRef | null
}

export interface TicketsResponse {
  desk_date_today: string
  resolved: number
  open: number
  tickets: Ticket[]
}

export interface Cash {
  account: string
  balance: number
  as_of: string
  desk_date_today: string
  pending_cash_requests_total: number
  balance_after_all_pending: number
}

export interface AgentEvent {
  seq: number
  ts: string
  event: string
  run_id?: string
  ticket_id?: number
  agent?: AgentName | 'system'
  depth?: number
  reasoning?: string
  detail: Record<string, any>
  summary: string
  importance: 'major' | 'minor'
}

export interface RunJob {
  run_id: string
  ticket_id: number
  status: 'running' | 'completed' | 'paused_for_budget_approval' | 'skipped' | 'error'
  started_at: string
  finished_at: string | null
}

export interface AgentSummary {
  agent: AgentName
  delegated_by: string[]
  delegated_to: string[]
  checks: string[]
  actions: string[]
  outcome: string
  tool_calls: number
}

export interface RunSummary {
  run_id: string
  ticket_id: number
  status: string
  started_at?: string
  finished_at?: string
  final_status?: string
  decision?: string
  next_steps_for_human?: string[]
  usage?: { total_tokens?: number; requests?: number }
  delegations?: number
  agents: AgentSummary[]
}
