import { statusOf } from '../status'
import type { Ticket } from '../types'

const TYPE_LABEL: Record<string, string> = {
  customer_order: 'Customer order',
  rent_notice: 'Rent notice',
  price_override: 'Price override',
}

export function TicketList({ tickets, selected, onSelect }: {
  tickets: Ticket[]
  selected: number | null
  onSelect: (id: number) => void
}) {
  return (
    <ul className="ticket-list">
      {tickets.map((t) => {
        const s = statusOf(t)
        return (
          <li key={t.id}>
            <button
              className={`ticket-card ${selected === t.id ? 'selected' : ''} ${t.is_resolved ? 'is-resolved' : ''}`}
              onClick={() => onSelect(t.id)}
            >
              <div className="ticket-top">
                <span className="ticket-id">#{t.id}</span>
                <span className={`pill ${s.tone}`}>{s.tone === 'resolved' ? '✓ ' : ''}{s.label}</span>
              </div>
              <div className="ticket-subject">{t.subject}</div>
              <div className="ticket-meta">{TYPE_LABEL[t.type] ?? t.type} · {t.requester}</div>
            </button>
          </li>
        )
      })}
    </ul>
  )
}
