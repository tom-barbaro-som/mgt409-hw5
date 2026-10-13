import type { AgentName } from './types'

export interface AgentMeta {
  id: AgentName
  name: string
  role: string
  icon: string
}

// Handsome Dan runs the desk; the rest of the team reports to him.
export const AGENTS: AgentMeta[] = [
  { id: 'boss', name: 'Boss', role: 'Handsome Dan · decides', icon: '🐶' },
  { id: 'inventory', name: 'Inventory', role: 'Stock & vendors', icon: '📦' },
  { id: 'accounting', name: 'Accounting', role: 'Cash & invoices', icon: '💵' },
  { id: 'facilities', name: 'Facilities', role: 'Lease & shop', icon: '🏛️' },
  { id: 'customer_service', name: 'Customer Service', role: 'Drafts replies', icon: '✉️' },
]

export const agentMeta = (id?: string) => AGENTS.find((a) => a.id === id)
export const agentName = (id?: string | null) => agentMeta(id ?? undefined)?.name ?? (id === 'system' ? 'Desk' : id ?? '')
