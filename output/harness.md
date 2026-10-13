# Campus Customs Operations Harness

This harness is the complete reference for the Campus Customs multi-agent operations system. It covers the database tables, MCP tools, agents, API routes, dashboard, safety rules, and the live resolution of tickets 101–103. The first sections (tables, ticket links, the first three tools) were written in Problems 2–3. Everything from "Agent team" onward reflects the system's final state after Problem 9.

- **Original (read-only):** `data/campus_customs.db`. Never modified; used only to reset.
- **Working copy:** `data/campus_customs_new.db`. All tools, the MCP server, and the backend read and write here.
- The two files had identical SHA-1 checksums (`f447ca6a…`) until the Problem 9 live run. The working copy then diverged through human-approved payments; `scripts/reset_db.py` (or **Reset demo data** on the dashboard) restores it.

## Database overview

| Table | Rows | Purpose |
|---|---|---|
| `desk` | 1 | The shop's "today" date and desk notes |
| `cash_accounts` | 1 | Cash available to pay expenses |
| `inventory` | 10 | Stock on hand per SKU and size |
| `pricing` | 4 | Unit cost and list price per SKU |
| `vendors` | 3 | Suppliers and their lead times |
| `invoices` | 1 | Bills owed to vendors |
| `leases` | 1 | Store space rent obligations |
| `payments` | 0 | Ledger of approved outgoing payments |
| `tickets` | 3 | Work requests the agents must resolve |
| `approval_requests` | created by the MCP server | The human approval queue (payments, POs, price overrides, message drafts, budget extensions). Exists only in the working copy. |

Dates are ISO `YYYY-MM-DD` text. The exception is `tickets.created_at`, an ISO timestamp with a time-zone offset (`-04:00`). Money values are `REAL` dollars.

---

## Tables and fields

### `desk`
The shop's operating clock. **Why it matters:** every agent must use this date, not the real calendar, to judge whether invoices are overdue, rent is due, or deliveries will arrive in time.

| Field | Type | Description | Why it matters to agents |
|---|---|---|---|
| `date_today` | TEXT, required | "Today" for Campus Customs (currently `2026-08-31`). | The reference date for overdue checks, rent due dates, and lead-time arrival estimates. |
| `notes` | TEXT | Free-form desk notes (currently empty). | A shared scratchpad where agents can leave context for each other or for the human manager. |

### `cash_accounts`
Money available to spend. **Why it matters:** the pay tool must check this balance before any payment and refuse if the payment would make the balance negative.

| Field | Type | Description | Why it matters to agents |
|---|---|---|---|
| `name` | TEXT, primary key | Account name (only `checking`). | The `payments.account` value must match this name, so a payment draws from a real account. |
| `balance` | REAL, required | Current balance (currently `$3,400.00`). | The hard ceiling on spending. Accounting deducts from it after each approved payment. |
| `date` | TEXT, required | Date the balance was last updated (`2026-08-31`). | Shows how current the balance is. Should be set to `desk.date_today` when a payment posts. |

### `inventory`
Stock on hand. Primary key is (`sku`, `size`). **Why it matters:** the Inventory agent uses it to check whether a customer order can be filled and when a reorder is needed.

| Field | Type | Description | Why it matters to agents |
|---|---|---|---|
| `sku` | TEXT, required | Product code, e.g. `CC-TEE-WHITE`. | The join key to `pricing` and to `tickets.sku`. |
| `name` | TEXT, required | Product name, e.g. "Classic Bulldog Tee". | A readable label for customer-facing drafts and the dashboard. |
| `size` | TEXT, required | `S`/`M`/`L`/`XL` for apparel, `OS` (one size) for hats and mugs. | Stock is tracked per size, so a ticket's `size` must match exactly. |
| `qty` | INTEGER, required | Units on hand. | Shows whether an order can be filled now or needs a vendor reorder. |
| `location` | TEXT, required | Shelf location (Aisle A to D). | Tells staff where to pick the item for fulfillment. |

Current stock: hoodie S 4 / M 8 / L 14 / XL 6 (32 in total); tee S **0** / M 5 / L 3 / XL 2; cap OS 40; mug OS **0**. There are no XS or XXL rows.

### `pricing`
Cost and retail price per SKU. **Why it matters:** this table supports discount decisions, margin checks, and estimates of reorder costs.

| Field | Type | Description | Why it matters to agents |
|---|---|---|---|
| `sku` | TEXT, primary key | Product code. | Joins to `inventory` and `tickets`. It is not declared as a foreign key, so tools must check that the SKU exists. |
| `unit_cost` | REAL, required | What the shop pays per unit. | The floor for any discount, and the basis for reorder cost estimates. |
| `list_price` | REAL, required | Standard retail price. | The starting point for quotes and price-override requests. |

| SKU | Cost | List | Margin |
|---|---|---|---|
| CC-HOOD-NAVY | $22.00 | $58.00 | $36.00 (62%) |
| CC-TEE-WHITE | $8.00 | $28.00 | $20.00 (71%) |
| CC-HAT-BLUE | $6.00 | $22.00 | $16.00 (73%) |
| CC-MUG-CREST | $3.50 | $14.00 | $10.50 (75%) |

### `vendors`
Suppliers. **Why it matters:** this table tells agents who can restock an item and how long it will take. A vendor with an open unpaid invoice will not ship new product.

| Field | Type | Description | Why it matters to agents |
|---|---|---|---|
| `id` | INTEGER, primary key | Vendor ID. | Referenced by `invoices.vendor_id`. Used to check whether the vendor has unpaid invoices. |
| `name` | TEXT, required | Vendor name. | Used in drafted (never sent) vendor communications and on the dashboard. |
| `specialty` | TEXT, required | What the vendor supplies. | There is no SKU-to-vendor table, so agents use this field to pick a vendor: apparel goes to vendor 1 and mugs to vendor 2. |
| `lead_days` | INTEGER, required | Days from order to delivery. | Estimated arrival = `desk.date_today` + `lead_days`. Customer Service uses this to set expectations. |

| id | Name | Specialty | Lead days |
|---|---|---|---|
| 1 | Bulldog Print Co | apparel reprint | 5 |
| 2 | Elm City Gifts | mugs and small goods | 3 |
| 3 | QuickShip CT | local courier | 1 |

### `invoices`
Money owed to vendors. **Why it matters:** an unpaid invoice is both a payment obligation and a block on new shipments from that vendor.

| Field | Type | Description | Why it matters to agents |
|---|---|---|---|
| `id` | INTEGER, primary key | Invoice number. | Referenced by `tickets.invoice_id` and `payments.ref_id`. |
| `vendor_id` | INTEGER, required, FK → `vendors.id` | Vendor that issued the invoice. | Identifies which vendor is blocked until the invoice is paid. |
| `amount` | REAL, required | Amount owed. | The payment amount. It must fit within `cash_accounts.balance`. |
| `due_date` | TEXT, required | Payment due date. | Overdue if `due_date < desk.date_today` and the status is `open`. |
| `status` | TEXT, required | `open` now; should become `paid` after an approved payment. | Agents filter on this to find unpaid bills and vendor blocks. |
| `description` | TEXT | What the invoice covers. | Links the invoice to a product need; invoice 501 is for a tee size S reprint. |

Invoice **501**: Bulldog Print Co, $840.00, due 2026-08-28, status `open`, "Rush reprint CC-TEE-WHITE S". It is **3 days overdue** as of the desk date.

### `leases`
Store rent obligations. **Why it matters:** the Facilities agent tracks rent due dates, and Accounting pays rent after human approval.

| Field | Type | Description | Why it matters to agents |
|---|---|---|---|
| `id` | INTEGER, primary key | Lease ID. | Referenced by `tickets.lease_id` and `payments.ref_id`. |
| `space_name` | TEXT, required | Space being leased ("Chapel Street shop"). | Identifies the lease on the dashboard and in drafted replies. |
| `landlord` | TEXT, required | Landlord ("Elm City Properties"). | The payee for rent payments. Replies to the landlord are drafted, never sent. |
| `monthly_rent` | REAL, required | Rent amount ($2,400.00). | The payment amount. It must fit within the cash balance. |
| `next_due` | TEXT, required | Next due date (2026-09-02, 2 days after the desk date). | Shows urgency. After rent is paid, this should advance one month (to 2026-10-02). |
| `notes` | TEXT | Free-form notes (empty). | A place to record payment confirmations or landlord context. |

### `payments`
Ledger of outgoing payments (empty now). **Why it matters:** every payment the human approves must add a row here. This is the audit trail that shows who approved each payment.

| Field | Type | Description | Why it matters to agents |
|---|---|---|---|
| `id` | INTEGER, primary key | Payment ID (auto-assigned). | Uniquely identifies each transaction for audit. |
| `kind` | TEXT, required | Payment type: `invoice` or `rent`. | Tells agents which table `ref_id` points to. |
| `ref_id` | INTEGER | ID of the invoice or lease being paid. | Links the payment to its obligation. It is polymorphic and has no foreign key, so tools must check that it exists. |
| `amount` | REAL, required | Dollars paid. | Deducted from the cash account. It must never exceed the account balance. |
| `account` | TEXT, required | Account paid from (`checking`). | Must match a `cash_accounts.name`. |
| `paid_at` | TEXT, required | Payment date. | Should be set to `desk.date_today`, not the real-world date. |
| `approved_by` | TEXT, required | Name of the human approver. | Enforces the human-approval rule: no payment may post without a human approver. |

### `tickets`
Incoming work requests. **Why it matters:** the Boss agent routes tickets to specialists, and the human manager watches them move to resolution on the dashboard.

| Field | Type | Description | Why it matters to agents |
|---|---|---|---|
| `id` | INTEGER, primary key | Ticket ID. | The unit of work the agents track and resolve. |
| `type` | TEXT, required | `customer_order`, `rent_notice`, or `price_override`. | Tells the Boss which specialist agent(s) should handle the ticket. |
| `requester` | TEXT, required | Who opened the ticket. | The recipient of the drafted reply. They are never contacted directly. |
| `subject` | TEXT, required | Short title. | A dashboard label. |
| `sku` | TEXT | Product involved, if any. | Joins to `inventory` and `pricing`. |
| `size` | TEXT | Size requested, if any. | Used with `sku` to find the exact inventory row. |
| `qty` | INTEGER | Quantity requested, if any. | Compared with `inventory.qty` to see whether stock covers the order. |
| `lease_id` | INTEGER, FK → `leases.id` | Related lease, if any. | Links rent tickets to the lease to pay. |
| `invoice_id` | INTEGER, FK → `invoices.id` | Related invoice, if any. | Links a ticket to the invoice that blocks it. |
| `status` | TEXT, required | `open` now; should become `resolved` (or similar) when done. | Tracks progress on the dashboard and lets agents skip finished work. |
| `notes` | TEXT | Request details. | Contains the actual ask. Agents can append their resolution notes here. |
| `created_at` | TEXT, required | ISO timestamp with time-zone offset. | Used to order and prioritize the queue. All three tickets were opened on 2026-08-31. |

Final ticket statuses: `open`, `in_progress`, `waiting_approval`, `blocked`, or `resolved`.

### `approval_requests` (operations table, added by the MCP server)
The queue of everything the agents drafted for a human. **Why it matters:** this is how "agents draft, humans decide" is enforced. Nothing in it takes effect until a human approves it on the dashboard.

| Field | Type | Description | Why it matters |
|---|---|---|---|
| `id` | INTEGER, primary key | Request id (#1, #2, …). | Shown on the dashboard and in agent reports. |
| `kind` | TEXT, CHECK | `payment`, `purchase_order`, `price_override`, `message`, or `budget_extension`. | Decides what approval does. |
| `ticket_id` | INTEGER, FK → `tickets.id` | Ticket the request serves. | Lets a ticket auto-resolve when its last request is decided. |
| `ref_id` | INTEGER | Invoice id, lease id, or vendor id (depending on kind). | Links a payment to its obligation, or a PO to its vendor. |
| `amount` | REAL | Dollar amount, always read from the database. | The cash a payment or PO would move. |
| `payload` | TEXT (JSON) | Details: payee, due date, SKU/size/qty, unit price/discount/margin, draft subject/body (`sent: false`), tokens. | What the human reviews. |
| `reason` | TEXT, required | The agent's justification. | Audit and human context. |
| `requested_by` | TEXT, required | Agent name, stamped by the backend. | Accountability; agents cannot impersonate each other. |
| `status` | TEXT | `pending`, then `approved` / `approved_not_sent` (messages) / `rejected`. | Drives the approval queue and ticket resolution. |
| `business_date`, `created_at` | TEXT | Desk date and real UTC time. | Business timeline vs. audit timeline. |
| `decided_by`, `decided_at`, `decision_note` | TEXT | The human's decision. | Proof of human approval. |

---

## How the three open tickets link to other tables

```
tickets.invoice_id ──► invoices.id ──► invoices.vendor_id ──► vendors.id
tickets.lease_id   ──► leases.id
tickets.sku/size   ──► inventory(sku, size), pricing.sku     (logical join, no FK)
payments.ref_id    ──► invoices.id or leases.id (chosen by payments.kind)
payments.account   ──► cash_accounts.name                    (logical join, no FK)
```

### Ticket 101: customer order (Tauhid Zaman, 1 × CC-TEE-WHITE size S)
- **inventory:** CC-TEE-WHITE size S has `qty = 0`, so the order can't be filled from stock.
- **invoices (via `invoice_id = 501`):** a $840 "Rush reprint CC-TEE-WHITE S" invoice from vendor 1. It was due 2026-08-28 and is **overdue and still open**.
- **vendors (via `invoices.vendor_id = 1`):** Bulldog Print Co, lead time 5 days. Because invoice 501 is unpaid, they **will not ship** the tee.
- **pricing:** list price $28.00 per tee.
- **Chain of work:** Accounting requests human approval to pay invoice 501 ($840), the payment is recorded, and the invoice is marked paid. That unblocks the vendor; the earliest arrival is 2026-09-05 (31 Aug + 5 days). Customer Service then drafts a reply to the customer with the expected date.

### Ticket 102: rent notice (Elm City Properties)
- **leases (via `lease_id = 1`):** Chapel Street shop, $2,400.00, due 2026-09-02 (in 2 days).
- **cash_accounts:** checking holds $3,400.00, so rent alone is affordable.
- **Chain of work:** Facilities confirms the lease details. Accounting requests human approval and pays $2,400. The payment is recorded, the balance is reduced, and `next_due` advances. Any reply to the landlord is drafted only.

### Ticket 103: price override (Yale AI Club, 20 × CC-HOOD-NAVY size M, bulk discount)
- **No FK links.** The ticket connects only through `sku`/`size` to `inventory` and `pricing`.
- **inventory:** only **8** size M hoodies are on hand, a shortfall of **12**. There are 32 hoodies across all sizes, but the club asked for M.
- **pricing:** cost $22.00 and list $58.00. Full price for 20 is $1,160; cost basis is $440. Any discount must stay above the $22 unit cost.
- **vendors:** a reprint comes from Bulldog Print Co (apparel, 5-day lead), which is **blocked by invoice 501**, the same invoice as ticket 101.
- **Chain of work:** Boss and Accounting decide on a discount, which needs human sign-off as a price override. Inventory reserves 8 and reorders 12 (about $264 at cost). Customer Service drafts a quote.

### Constraints that span the tickets
- **Invoice 501 blocks two tickets.** Paying it unblocks the vendor for both ticket 101 and ticket 103.
- **Cash is tight:** $3,400 − $840 (invoice 501) − $2,400 (rent) = **$160 left**. That is not enough to pay for a ~$264 hoodie reorder, so the pay tool would refuse it. Agents and the human manager must decide priorities: rent is due in 2 days, and the invoice is already overdue. No payment may bring the balance below $0.
- **No external contact:** every reply to the customer, landlord, vendor, or student club is drafted and never sent.
- **Not linked to any ticket:** CC-MUG-CREST is out of stock (`qty = 0`). It is a possible restock item from vendor 2 (Elm City Gifts, 3-day lead).

---

## MCP server tools (Problem 3)

The FastMCP server in `mcp_server/server.py` is the single shared toolbox for all agents. It reads `data/campus_customs_new.db`. All three initial tools are **read-only** and return only values from the database. A missing record returns `found: false` instead of an invented answer.

### `check_inventory(sku, size=None)`
- **Reads:** `inventory`
- **Tickets:** 101 and 103
- **Why:** It shows that ticket 101's Classic Bulldog Tee in size S has 0 on hand and ticket 103's hoodie in size M has only 8 of the 20 requested, so neither order can be filled from stock without a reorder.

### `get_invoice_status(invoice_id)`
- **Reads:** `invoices`, `vendors`, `desk`
- **Tickets:** 101 (and 103 indirectly)
- **Why:** For ticket 101's linked invoice 501, it reports that the $840 Bulldog Print Co bill is 3 days overdue as of 2026-08-31 and that the vendor is blocked from shipping the size S tee (5-day lead time), which is the same vendor block that stops ticket 103's hoodie reorder.

### `get_lease_details(lease_id)`
- **Reads:** `leases`, `desk`
- **Tickets:** 102
- **Why:** For ticket 102's rent notice, it confirms that lease 1 (Chapel Street shop, Elm City Properties) owes $2,400 due 2026-09-02, which is 2 days after the desk date, so Accounting knows the exact amount and urgency before requesting payment approval.

---

## Agent team

Built with **PydanticAI** on **gpt-6-luna** through Portkey (Responses API, low reasoning effort, concise reasoning summaries, 4,000 output tokens max per response). The Portkey key is loaded from the class-root `Portkey.env` by relative path and is never printed. Any other model is rejected at startup.

| Agent | Files | Role | Output | MCP tools it may use |
|---|---|---|---|---|
| **Boss** (Handsome Dan on the dashboard) | `backend/agents/boss.py`, `prompts/boss.md` | Reads the ticket, routes it to 1–2 teammates in sequence, weighs cash and priorities across tickets, makes the final decision, sets status | `TicketDecision` | all read tools, `add_ticket_note`, `set_ticket_status` |
| **Inventory** | `agents/inventory.py`, `prompts/inventory.md` | Stock by SKU + size, shortages, vendor match by specialty, blocked status and lead time, shortage-only PO drafts, spotting items already on order | `AgentReport` | read tools, `add_ticket_note`, `draft_purchase_order` |
| **Accounting** | `agents/accounting.py`, `prompts/accounting.md` | Cash, invoices, overdue status, margins and discount guideline; files payment, PO, and price-override requests; always files payment for a blocking invoice | `AgentReport` | read tools, `add_ticket_note`, `request_payment`, `request_price_override`, `draft_purchase_order` |
| **Facilities** | `agents/facilities.py`, `prompts/facilities.md` | Leases, rent due dates, landlord notices (checked against the DB), space and maintenance | `AgentReport` | read tools, `add_ticket_note` |
| **Customer Service** | `agents/customer_service.py`, `prompts/customer_service.md` | Drafts every outward message; never sends; never reveals internal cash or vendor issues | `AgentReport` | read tools, `add_ticket_note`, `draft_message` |

All agents also load `prompts/shop_rules.md`, the shop rules shared by every agent. Data types are in `backend/models.py`, and the orchestration is in `backend/team.py`.

**Agent loop and delegation (full connectivity, used sparingly)**
- `OperationsTeam.run_ticket(id)` runs the Boss's PydanticAI loop (`agent.iter`: model → MCP tools → model … → structured output).
- Every agent has `delegate_task(to_agent, task, reason)`, so **any agent can delegate to any other**. The delegate runs its own loop and returns an `AgentReport`.
- Delegation is **sequential** (`sequential=True`, one at a time), and each agent may use at most **2 different teammates per ticket**. The Boss routes:
  - Customer order: Inventory (which brings in Accounting if an invoice blocks the vendor), then Customer Service.
  - Rent notice: Facilities, which brings in Accounting.
  - Price override: Accounting, which brings in Inventory, then Customer Service.
- Before finishing, the Boss must confirm that every blocking invoice has a payment request; otherwise the human would have nothing to approve.
- All agents on a ticket share one usage counter and one token budget, and one MCP connection (from `.mcp.json`), with a role-filtered tool view per agent.

## MCP tools (final: 20 tools in `mcp_server/server.py`)

The MCP server is the **only** layer that touches shop data, and it reads and writes `data/campus_customs_new.db`. Tags: `read` (every agent), `agent-write` (drafts and requests only), `system` (backend), `human-only` (approve/reject; never given to agents).

| Tool | Group | Tables | Tickets | Why / behavior |
|---|---|---|---|---|
| `check_inventory(sku, size?)` | read | inventory | 101, 103 | Tee S = 0 (101); hoodie M = 8 of 20 (103). |
| `get_invoice_status(invoice_id)` | read | invoices, vendors, desk | 101, 103 | Invoice 501: $840, 3 days overdue, blocks Bulldog Print Co (5-day lead). |
| `get_lease_details(lease_id)` | read | leases, desk | 102 | Lease 1: $2,400 due 2026-09-02 (2 days from the desk date). |
| `list_tickets(status)` | read | tickets | all | The queue, so the Boss can weigh tickets against each other. |
| `get_ticket(ticket_id)` | read | tickets + linked rows + approval_requests | all | One call shows the ticket, its links, and every request already filed. |
| `get_cash_balance()` | read | cash_accounts, approval_requests | all | Balance, pending cash-out requests itemized, and which POs are blocked until an invoice is paid. |
| `list_vendors()` | read | vendors, invoices | 101, 103 | Specialty, lead days, open invoices, `blocked`. |
| `list_invoices(status?)` | read | invoices, vendors | 101 | Open or overdue bills. |
| `get_pricing(sku, qty, unit_price?)` | read | pricing | 103 | Cost $22 vs list $58; margin at a proposed price. |
| `list_approval_requests(...)` | read | approval_requests | all | Prevents duplicates; shows human decisions and notes. |
| `list_payments()` | read | payments | 101, 102 | Confirms what was actually paid. |
| `add_ticket_note` | agent-write | tickets.notes | all | Appends a dated, signed line; existing notes are never erased. |
| `set_ticket_status` | agent-write (Boss; backend as `system`) | tickets | all | Refuses `resolved` while approvals are pending. |
| `request_payment` | agent-write | approval_requests | 101, 102 | Amount from the DB. Refuses duplicates or closed invoices. The funds check ignores POs that depend on the invoice being paid. |
| `draft_purchase_order` | agent-write | approval_requests | 103 | Shortage qty × unit cost. Returns `must_pay_first` (blocking invoices plus any payment request for each). |
| `request_price_override` | agent-write | approval_requests | 103 | Refuses prices below unit cost or at/above list price. |
| `draft_message` | agent-write | approval_requests | 101, 103 | Saves a draft; `sent: false` always. |
| `request_budget_extension` | system | approval_requests | any | Filed by the backend when a ticket's AI budget runs out. |
| `approve_request` | **human-only** | approval_requests, cash_accounts, payments, invoices, leases | 101, 102, 103 | The only way money moves. Refuses short cash (no negative balances) and POs to blocked vendors (naming the invoice and its payment request). Rejects agent names as approvers. |
| `reject_request` | **human-only** | approval_requests | any | Declines a request with a reason the agents read on their next run. |

## Backend API routes (`backend/main.py`, FastAPI, `uvicorn main:app --reload --port 8000` from `backend/`)

| Method & route | What it does |
|---|---|
| `GET /api/health` | Reports whether the server is up, whether gpt-6-luna/Portkey is configured, and any run in progress. |
| `GET /api/tickets` | Returns all tickets with `is_resolved`, a one-line explanation, approval requests, and `last_run`. |
| `GET /api/tickets/{id}` | Returns one ticket with its explanation, linked records, approvals, and last run. |
| `POST /api/tickets/{id}/run` | Starts the agent team on a ticket in the background (one run at a time; 409 if busy). |
| `GET /api/runs` | Lists runs started since the server came up. |
| `GET /api/runs/{run_id}` | Returns one run's status, the Boss's decision, and token usage. |
| `GET /api/runs/{run_id}/summary` | Returns a brief per-agent summary of a run, built from the audit trail (no model calls). |
| `GET /api/events` | Returns audit events with a brief `summary`, an `importance` tag (`major`/`minor`), and a `seq` cursor for polling. |
| `GET /api/approvals` | Returns the approval queue: payments first; POs carry their live blocking invoices. |
| `POST /api/approvals/{id}/approve` | Human approval through the human-only MCP tool; logs a `human_decision` and auto-resolves the ticket when nothing is left pending. |
| `POST /api/approvals/{id}/reject` | Human rejection with a reason; same logging and auto-resolve. |
| `GET /api/cash` | Returns the checking balance from `cash_accounts`, plus pending requests and the balance after them. |
| `POST /api/reset` | Restores the working DB from the original (requires `{"confirm": true}`; refused during a run). |

CORS allows the Vite dashboard (`http://localhost:5173`) and other local ports only.

## Dashboard (`frontend/`, React + Vite + TypeScript; `npm run dev` opens http://localhost:5173)

Full design rationale is in `output/design.md`.
- **Layout:** three columns (Tickets · selected ticket · **Needs your OK**) under a Yale-blue header with a Handsome Dan badge.
- **Tickets:** each card has one status pill: Open → Agents working → Run complete · needs you → ✓ Resolved (resolved cards dim). A ticket auto-resolves when its run is complete and its last pending request has been decided.
- **Start agent work:** one button per selected ticket; disabled while another ticket is running.
- **Live view:** one lane per agent (Not involved / Working / Waiting on X / Done, plus its latest line) and a feed of **major** steps only: reasoning sentences, delegations, write actions, refusals, and conclusions. It polls the audit trail every ~1.2 s, so monitoring uses no extra tokens.
- **After a run:** a brief per-agent summary replaces the feed (path, tokens, duration, actions, checks, conclusion).
- **Approvals:**
  - Money requests show the balance impact ("Checking $1,000 → $160") and warnings (insufficient cash, or a blocking invoice with its payment request number). They require a second **Yes, pay** click.
  - Rejections require a reason.
  - Drafts show "will not be sent".
  - The approver's name is recorded on every decision.
- **Live checking balance:** polled every 2 s. It flashes with the delta ("−$840.00 just now") only when money actually moves, and shows how much is still awaiting approval.
- **Reset demo data:** in the footer, behind a confirmation dialog.

## Audit trail (`output/audit_trail.json`)
- **Append-only JSON Lines:** one object per line, file opened only in append mode, never rewritten.
- Events: `db_reset`, `ticket_run_started`, `agent_started`, `model_step` (the agent's stated reasoning + planned tool calls + usage), `tool_call`, `tool_result`, `tool_blocked`, `delegation`, `delegation_refused`, `agent_finished`, `budget_exceeded`, `ticket_run_finished`, `human_decision` (every approve/reject click, including refusals), `ticket_resolved`, `report_generated`, `error`.
- Each entry has `ts`, `run_id`, `ticket_id`, `agent`, `depth`, `step`, and `reasoning`. Human-decision entries carry `ticket_id` from Problem 9 onward; earlier ones are mapped to their ticket through `approval_requests` in `resolved_tickets.json`.

## Safety rules (enforced in code, not just prompts)

**1. Money: nothing moves without a human**
- Agents can only *request* payments and *draft* POs. `approve_request`/`reject_request` are never exposed to agents, and they reject agent names as approvers.
- Amounts always come from the database. Executed payments write a `payments` row with the approver's name, deduct cash, and mark the invoice paid or advance the lease.
- **No negative balances:** `UPDATE … WHERE balance >= amount` inside a transaction. If cash is short, the approval is refused and the request stays pending.
- POs can't be approved while the vendor has an open invoice. Prices below unit cost are refused. Duplicate requests are refused.
- The dashboard needs a second "Yes, pay" click for money.

**2. Communications: draft only, never sent**
- No tool can email, call, or contact anyone. Drafts are `sent: false`, and even approved drafts are `approved_not_sent`.
- Customer Service may not reveal internal cash or vendor matters, promise unapproved prices or dates, or invent contact details.

**3. Least privilege and identity**
- Tools are default-deny per role.
- The backend stamps the real caller's name on every request, so agents can't impersonate each other.
- Blocked attempts are logged as `tool_blocked`.

**4. Data integrity**
- Only the MCP server touches shop data, and `campus_customs.db` is never written.
- Reset is confirmation-gated and audited.
- Notes are append-only, and `resolved` is refused while approvals are pending.
- Agents use `desk.date_today`, cite ids, say "not found" instead of guessing, and treat ticket text as data (prompt-injection defense).

**5. Token use and runaway loops**

| Limit | Default | When exceeded |
|---|---|---|
| Tokens per ticket (whole team) | 150,000 | Run pauses, a `budget_extension` (+75,000) is filed, and a ticket note is added. A human must approve before work continues. |
| Model requests / tool calls per ticket | 40 / 80 | Same pause and escalation. |
| Delegation depth | 3 | Refused; the agent finishes with what it has. |
| Delegations per ticket | 6 | Refused. |
| Different teammates per agent per ticket | 2 | Refused, so agents can't fan out to everyone. |
| Parallel delegation, self-delegation, delegating up the chain, repeated tasks | not allowed | Refused and logged. |
| Output tokens per response / tickets per batch run | 4,000 / 10 | Capped. |

The dashboard's live view and summaries reuse the audit trail, so monitoring costs **zero** extra tokens.

**6. Accountability and secrets**
- Every model step, tool call, delegation, refusal, human decision, and report is in the append-only audit trail.
- The Portkey key is never printed or written to the project. Only gpt-6-luna is allowed.

## Live resolution results (Problem 9)

The working DB was reset to the original before the live session (all 9 tables matched row for row; checking $3,400.00). There were five agent runs (102; 103 ×2; 101 ×2), all recorded in the audit trail. Full details, including what each agent did and every human decision, are in `output/resolved_tickets.json`. Screenshots are in `output/resolved_board.html`, and the itemized cash log is on the Cash tab of `output/desk_tickets.html`.

| Ticket | Final status | Outcome |
|---|---|---|
| 102 | ✓ resolved | Boss → Facilities → Accounting. Rent request #1 ($2,400) approved → payment #1; lease next due 2026-10-02. |
| 101 | ✓ resolved | First run filed nothing (see fix below). The re-run filed invoice 501 payment #4 ($840) and draft #5. Both were approved; payment #2 was posted and the vendor unblocked. The draft was **not sent**. The reprint's delivery isn't tracked (est. 2026-09-05). |
| 103 | **waiting_approval (not resolved)** | Price override #3 ($49.00/unit, 15.5% off) approved. PO #2 (12 hoodies, $264) is still pending: 4 approvals were refused while invoice 501 blocked the vendor, then 2 refused for insufficient cash ($160). |

**Cash reconciliation:** $3,400.00 − $2,400.00 − $840.00 = **$160.00**. This matches the ledger, `cash_accounts` in the working DB, and the live dashboard (`GET /api/cash`). $264.00 is pending and unpaid.

## Change history
- **P5:** built the agent team, grew the MCP server from 3 to 20 tools, added the approval queue table, the append-only audit trail, and the token/loop guardrails.
- **P6:** delegation changed to 1–2 teammates per agent, in sequence (code-enforced).
- **P7:** FastAPI routes. Agents load the model lazily, so the read and approval routes work without it.
- **P8:** dashboard; run summaries; event `importance`; auto-resolve; CORS for 5173.
- **P9:**
  - **Blocking-invoice fix:** Accounting had refused to file invoice 501's payment because "cash after pending" counted a PO that *depends* on that invoice. Now:
    - the funds check excludes dependent POs;
    - the tools return `must_pay_first`;
    - Accounting must always file a blocking invoice's payment;
    - the Boss verifies it before finishing;
    - the dashboard shows "Approve payment request #N first".
  - Human decisions now carry `ticket_id`.
  - Added the reporting scripts (`scripts/capture_board.py`, `scripts/build_resolution_report.py`).
