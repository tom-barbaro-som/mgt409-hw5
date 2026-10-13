# Campus Customs MCP Server

This is the shared toolbox for the Campus Customs multi-agent operations team, and the **only layer that reads or writes shop data**. Every agent (Boss, Inventory, Accounting, Facilities, Customer Service) reaches the database exclusively through these tools. The backend has no separate shop-data code path. Built with [FastMCP](https://gofastmcp.com) (v4).

## How it works

- `server.py` creates a `FastMCP` server named `campus-customs` and registers 20 tools with `@mcp.tool`.
- Clients connect over **stdio** using the config in `hw5/.mcp.json`. Its paths are relative to `hw5/`, so it works in any clone. Claude Code uses it, and so does the PydanticAI backend (`backend/mcp_client.py`), which resolves the paths against `hw5/`.
- **Database:** the server only touches the **working copy** `data/campus_customs_new.db`, which it finds relative to its own location. The original `data/campus_customs.db` is never opened. To restart from the original, run `scripts/reset_db.py`.
  - `CAMPUS_DB_PATH` can point the server at another copy. This is used only for tests.
- **Read tools** open SQLite in `mode=ro` and can't change anything.
- **Write tools** run inside `BEGIN IMMEDIATE` transactions, so a refusal or error leaves no partial change.
- **Shop date:** every date calculation uses `desk.date_today` (currently 2026-08-31), not the real-world date.
- **No invented data:** values come from the database, plus simple arithmetic on them (days overdue, totals, margins, arrival = today + lead_days). Amounts for payments and POs are always read from the database, never typed in by an agent. A missing record returns `found: false` or `ok: false` with an error.
- **No external contact:** no tool sends email or contacts anyone. `draft_message` only saves a draft.

### Operations table
The first write call creates one extra table in the working copy, **`approval_requests`**. It is the queue a human works through on the dashboard: payments, purchase orders, price overrides, message drafts, and token-budget extensions.

| Column | Meaning |
|---|---|
| `id`, `kind` | Request id. `kind` is `payment`, `purchase_order`, `price_override`, `message`, or `budget_extension`. |
| `ticket_id`, `ref_id`, `amount` | Linked ticket; invoice, lease, or vendor id; dollar amount (from the DB). |
| `payload` | JSON details (payee, SKU/size/qty, draft subject/body, margins, expected arrival, …). |
| `reason`, `requested_by` | Why the request was filed, and by which agent. |
| `status` | `pending`, then `approved` / `approved_not_sent` (messages) / `rejected`. |
| `business_date`, `created_at` | Desk date, and the real UTC timestamp. |
| `decided_by`, `decided_at`, `decision_note` | The human decision. |

## Access groups

| Tag | Who may call | Purpose |
|---|---|---|
| `read` | every agent | Lookups only |
| `agent-write` | agents (backend role allowlist) | Notes, status, **drafts and requests**. None of these move money or contact anyone. |
| `system` | backend only | Token-budget escalation |
| `human-only` | human via dashboard/backend, **never agents** | Approve or reject. Approval is the only path by which money moves. |

## Tools

### Read (11)
| Tool | Tables read | Returns |
|---|---|---|
| `check_inventory(sku, size?)` | inventory | Rows (name, size, qty, location) and `total_qty` |
| `get_invoice_status(invoice_id)` | invoices, vendors, desk | Invoice with vendor and lead time; `is_overdue`, `days_past_due`, `vendor_blocked` |
| `get_lease_details(lease_id)` | leases, desk | Lease fields, `days_until_due`, `is_past_due` |
| `list_tickets(status="open")` | tickets, desk | The ticket queue (null = all) |
| `get_ticket(ticket_id)` | tickets + linked leases, invoices, vendors, inventory, pricing, approval_requests | Everything a ticket points at, in one call |
| `get_cash_balance()` | cash_accounts, desk, approval_requests | Balances, pending cash-out requests, `balance_after_all_pending` |
| `list_vendors()` | vendors, invoices, desk | Specialty, lead_days, open invoices, `blocked`, earliest arrival if ordered today |
| `list_invoices(status?)` | invoices, vendors, desk | Invoices with overdue flags |
| `get_pricing(sku, qty=1, unit_price?)` | pricing | Cost, list price, margin at list and at a proposed price; `proposed_below_cost` |
| `list_approval_requests(status="pending", ticket_id?, kind?)` | approval_requests | The approval queue |
| `list_payments()` | payments | Ledger of approved payments and `total_paid` |

### Agent write (7): drafts and requests only
| Tool | Writes | Guardrails |
|---|---|---|
| `add_ticket_note(ticket_id, note, agent)` | tickets.notes | Appends a dated, signed line; existing notes are never erased |
| `set_ticket_status(ticket_id, status, reason, agent)` | tickets.status, notes | **Boss only**; refuses `resolved` while approvals are pending |
| `request_payment(payment_kind, ref_id, reason, ticket_id?, account="checking", requested_by)` | approval_requests | Amount from the invoice or lease; refuses unknown, closed, or duplicate items; returns a funds check |
| `draft_purchase_order(vendor_id, sku, size, qty, reason, ticket_id?, requested_by)` | approval_requests | Cost = qty × unit_cost; qty 1–500; refuses duplicates; flags blocked vendors |
| `request_price_override(sku, qty, unit_price, reason, ticket_id?, size?, requested_by)` | approval_requests | **Refuses below unit cost** or at or above list price; reports discount and margin |
| `draft_message(recipient, subject, body, reason, ticket_id?, channel="email", drafted_by)` | approval_requests | **Never sends**: `sent: false` |
| `request_budget_extension(ticket_id, tokens_used, tokens_requested, reason, requested_by)` | approval_requests | `system` tag: called by the backend when a ticket's AI budget is exhausted |

### Human only (2): never exposed to agents
| Tool | Effect |
|---|---|
| `approve_request(approval_id, approved_by, note?)` | **payment:** refuses if cash is short (no negative balances); otherwise deducts cash, inserts a `payments` row (`approved_by` = the human), and marks the invoice `paid` or advances `leases.next_due` by a month. **purchase_order:** refuses while the vendor has an open invoice or cash is short; otherwise pays the PO cost and records the expected arrival (nothing is sent to the vendor). **price_override:** approved. **message:** `approved_not_sent`. **budget_extension:** approved. Agent names are rejected as approvers. |
| `reject_request(approval_id, rejected_by, reason)` | Marks the request rejected. Agents read the reason on their next run. |

## Setup and running

From the `hw5` folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python mcp_server/server.py        # stdio server (normally launched by Claude Code or the backend via .mcp.json)
python scripts/reset_db.py         # restore campus_customs_new.db from the original
```
