# Problem 1: Vibe coder prompts

## User prompt

```text
For this conversation, we will work exclusively in the Homework 5 folder unless otherwise specified.

Campus Customs is a New Haven store that sells Yale-related merchandise. We are going to create their Muti-Agent Operations team. Through this project, we will make an MCP server, FastAPI backend (with multi-agent team), and a React dashboard so a human manager can observe the agents and approve requests.

The agent team has full connectivity, meaning any agent may delegate tasks to any other agent. Later on, we will build 5 agents: Boss, Inventory, Accounting, Facilities, and Customer Service.

In the hw5 folder, there is a data folder that includes the shop's database. Our tools will update the database (data/campus_customs_new.db) and direct the MCP server and backend to work on that working copy. Please preserve campus_customs.db as an original, in the event we need to restart from the provided database.

There are rules of the shop we need to account for.

* The field desk.date_today is "today" from the perspective of Campus Customs - use this date for determining if invoices are overdue
* Vendor lead times are provided in the vendors table
* Vendors will not ship new product if there is an open unpaid invoice
* Human approval is required for all payments. When a payment is made, the relevant table must be updated to reflect the transaction
* If the relevant account does not have enough cash for a transaction, the pay tool must refuse. There cannot be negative account balances
* In this work, cash will only go "out" (expenses) - we will not model revenue
* Before a full run to resolve tickets, be sure to reset the "new" database to the unmodified original values
* DO NOT email/contact/call customers or vendors. No external contact at all. If there are emails in this assignment, draft them - but they are NEVER sent
* Use my PORTKEY_API_KEY for AI calls, using only gpt-6-luna. Only use this model for agents and their chats. Information on using my PortKey key is in the root (I believe in an .env file). Do not post or share my Portkey - use relative references to access it when needed


Problem 1: Vibe coder prompts
Create a file called AI_prompts.md that tracks our full conversation. Append it with new prompts and responses as we work. Include my full prompts in my own words. Label each section of the file with problem numbers and titles
```

## Assistant response

Created `AI_prompts.md` in `Homework/hw5`. The log is organized by problem number and title. Each section has your full prompt, word for word, and a short summary of my response. I'll add a new section for each prompt as we go.

I also created the working database `data/campus_customs_new.db` as an exact copy of `data/campus_customs.db`. Matching SHA-1 checksums confirm the copy is identical. The original will not be modified. The database has nine tables: `cash_accounts`, `desk`, `inventory`, `invoices`, `leases`, `payments`, `pricing`, `tickets`, and `vendors`.

I noted the shop rules for later problems: `desk.date_today` is "today"; vendor lead times come from `vendors`; vendors won't ship while an invoice is unpaid; every payment needs human approval and must update the database; payments can never make a balance negative; only expenses are modeled; reset the working database before a full run; there is no external contact, so emails are drafted and never sent. AI calls will use only `gpt-6-luna` through Portkey. The key will be loaded by relative path from `Portkey.env` in the class root and will never be printed or committed.

# Problem 2: Study the Campus Customs database

## User prompt

```text
Problem 2: Study the Campus Customs database
Review each table in data/campus_customs.db. Review all fields. Copy the original file to data/campus_customs_new.db, which we will update in future problems. "_new" will serve as our working copy.

Observe how the three open tickets link to other tables in the database.

Create output/harness.md and list each table in the database. Also, describe each field for each table and include a sentence on why each table and field is important for the agents to use later. This harness file will be appended as we work
```

## Assistant response

Reviewed all 9 tables and every row of `campus_customs.db` without changing it. `data/campus_customs_new.db` (copied in Problem 1) still has the same checksum as the original. Created `output/harness.md`. It contains a table overview with row counts, a description of every field, a sentence on why each table and field matters to the agents, and a map of how the three open tickets link to other tables.

Findings:
- **Ticket 101** (tee, size S): stock is 0, and the ticket links to invoice 501 ($840, Bulldog Print Co). That invoice is 3 days overdue as of the desk date (2026-08-31), so the vendor won't ship until it is paid. Lead time is 5 days.
- **Ticket 102** (rent): links to lease 1, $2,400 due 2026-09-02.
- **Ticket 103** (20 hoodies, size M, bulk discount): only 8 size M are in stock. The reorder would come from the same vendor, which invoice 501 blocks. Any discount must stay above the $22 unit cost.
- **Cash:** $3,400 − $840 − $2,400 leaves $160, which is not enough for the ~$264 hoodie reorder. The human manager will need to set priorities.

# Problem 3: Build the MCP server

## User prompt

```text
Problem 3: Build the MCP server
Generate an MCP server in mcp_server/ using FastMCP. This server will interact with data/campus_customs_new.db, but we do not need to connect or run the MCP in this problem.

Every agent in this project will leverage tools from this specific MCP server. Tools will be added as we work together in future problems. Initially, create three tools with clear names that you know the agents will need for handling tickets in the database. Do not invent or create new data, only use information from the database.

Append output/harness.md to explain these three MCP tools. For each tool, explain which table it reads, which ticket it helps handle (101, 102, or 103), and add a sentence (only 1 sentence) explaining why this tool helps with the specified ticket(s). Be sure to tie the tool specifically to a ticket, not just a general/vague explanation.

Create mcp_server/README.md that explains the MCP server, how it works, what is can read, and the tools it has.
```

## Assistant response

Created a local `.venv` in `hw5`, installed FastMCP 4.0.11, and added `requirements.txt`. Built `mcp_server/server.py` with three read-only tools. They open `data/campus_customs_new.db` with SQLite `mode=ro` and use `desk.date_today` as "today":
- `check_inventory(sku, size)` reads `inventory` and serves tickets 101 and 103.
- `get_invoice_status(invoice_id)` reads `invoices`, `vendors`, and `desk`. It serves ticket 101 (and ticket 103 through the vendor block) and reports days overdue and whether the vendor is blocked.
- `get_lease_details(lease_id)` reads `leases` and `desk`, serves ticket 102, and reports days until rent is due.

Appended a "MCP server tools" section to `output/harness.md`. For each tool it lists the tables read, the ticket(s) served, and one sentence tied to the ticket. Created `mcp_server/README.md`. The server was not started or connected. I tested the tools once with FastMCP's in-memory client: tee S = 0, hoodie M = 8, invoice 501 is 3 days overdue with vendor 1 blocked, rent of $2,400 is due in 2 days, and unknown IDs return `found: false`. Both database files kept their original checksums.

# Problem 4: Add the MCP server to vibe coder and test each tool

## User prompt

```text
Problem 4: Add the MCP server to vibe coder and test each tool
Add the MCP server to this project in Claude Code so you can call each tool. Save the the connection JSON text in .mcp.json in hw5 so I can refer back to it later as needed.

Once this connection exists, test each of the three existing MCP tools. Save evidence of each test in output/mcp_smoke.json. For each test, include the prompt you used to test the tool, the tool name, and the tool output (which must match values in data/campus_customs_new.db, which should theoretically be updated by the tool call itself)
```

## Assistant response

Created `hw5/.mcp.json`, Claude Code's project-scoped MCP config. It registers the `campus-customs` stdio server with the `hw5/.venv` Python and `mcp_server/server.py`, and points `CAMPUS_DB_PATH` at `data/campus_customs_new.db`. Claude Code loads `.mcp.json` only when a session starts in that folder. This session started at the class root, so the tools could not be loaded into it during the conversation.

To test the connection, added `scripts/mcp_smoke.py`. It launches the server from the `.mcp.json` config over a real MCP stdio connection, lists the tools, calls each one, and checks each output against a direct SQL query on `campus_customs_new.db`. Results are in `output/mcp_smoke.json`. There were 4 tests: `check_inventory` for ticket 101 (tee S = 0) and ticket 103 (hoodie M = 8), `get_invoice_status(501)` for ticket 101 (3 days overdue, vendor blocked), and `get_lease_details(1)` for ticket 102 ($2,400 due in 2 days). Each test records its prompt, tool name, arguments, and output. All 4 matched the database. The three tools are read-only, so the database checksum was the same before and after.

## User prompt

```text
Yes, please start the session an dredo the smoke test
```

## Assistant response

Moved this Claude Code session into `Homework/hw5`. That made Claude Code load `hw5/.mcp.json`, and after the user approved it, the `campus-customs` server's three tools became available. Called each tool natively from Claude Code:
- `check_inventory(CC-TEE-WHITE, S)` returned qty 0.
- `check_inventory(CC-HOOD-NAVY, M)` returned qty 8.
- `get_invoice_status(501)` returned $840 open, 3 days overdue, Bulldog Print Co blocked, 5-day lead time.
- `get_lease_details(1)` returned $2,400 due 2026-09-02, 2 days away.

Rewrote `output/mcp_smoke.json` with these native calls as the evidence. Each test records its prompt, tool name, arguments, verbatim output, and the matching SQL rows from `campus_customs_new.db`. All 4 matched. The working copy still has the same checksum as the original because the tools are read-only. `scripts/mcp_smoke.py` remains available as a scripted re-run.

# Problem 5: Build the agent team and grow the MCP tools

## User prompt

```text
Problem 5: Build the agent team and grow the MCP tools
Create the agentic team using PydanticAI:

* Boss: reads each ticket, delegates which agent should work on it, and makes final decisions
* Inventory: verifies stock by SKU and size, identified shortages, and determines which vendor can restock as needed
* Accounting: observes cash and invoices, checks margins, and drafts payments/purchase orders for human approval
* Facilities: manages the physical shop and its requirements (e.g., leases, rent)
* Customer Service: drafts messages for customers that are NOT SENT without human approval


When creating the agents, include prompts, models (gpt-6-luna), and agent loops so they can delegate and effectively work together with full connectivity.

Write the agent prompts in backend/prompts/ - creating one file per agent. Save data types in backend/models.py, and the agent files under backend/

Use my PortKey API Key, as discussed in the first prompt in this project.

Make the agent prompts detailed enough to cover all reasonable cases based on the existing database tickets, and what you might guess could be necessary to fully define roles and responsibilities.

Add more tools for the agents in the MCP server so they can start to resolve tickets. Important: the shop's "source of truth" is data/campus_customs_new.db - do not create a second shop-tools layer that bypasses the MCP.

Ensure the agents append output/audit_trail.json as they operate. For each agent-loop step, each agent should record what they are doing/their reasoning so this data could be audited later. Only append text to this audit trail file - never erase what is already there.

Append output/harness.md to list each agent and MCP tool. This update should include all agents and new tools from this prompt. Also, add a safety section that creates guardrails that a real business would want. The safety section should address topics like drafting and NOT SENDING messages or money without human approval. Also have rules in place to limit token "over-use" (or make a human approve more work if the agents are using a lot of tokens).

Update mcp_server/README.md so it is consistent with the full tool list after this prompt
```

## Assistant response

**MCP server (17 new tools, 20 in total), still the only shop-data layer:**
- 8 new read tools: `list_tickets`, `get_ticket`, `get_cash_balance`, `list_vendors`, `list_invoices`, `get_pricing`, `list_approval_requests`, `list_payments`.
- 6 agent-write tools that only draft or request: `add_ticket_note`, `set_ticket_status` (Boss only), `request_payment`, `draft_purchase_order`, `request_price_override`, `draft_message` (never sends).
- 1 system tool: `request_budget_extension`.
- 2 human-only tools: `approve_request` and `reject_request`. Approval is the only way money moves. It refuses negative balances, POs to blocked vendors, and agent names as approvers, and it records a `payments` row and updates the invoice or lease.
- A new `approval_requests` table in the working copy holds the human approval queue.

**Agents (PydanticAI, gpt-6-luna via Portkey; the key is loaded from `Portkey.env` and never printed):**
- One file per agent in `backend/agents/` and one prompt per agent in `backend/prompts/`, plus a shared `shop_rules.md`.
- Data types are in `backend/models.py`.
- `backend/team.py` runs each agent loop with `agent.iter`. Every agent has `delegate_task`, so any agent can delegate to any other, with depth, count, and no-cycle guards.
- Agents reach the database only through the MCP server, with a role allowlist and the backend stamping each caller's identity on its requests.

**Audit trail:** `output/audit_trail.json` is append-only JSON Lines. It logs every model step (with the agent's stated reasoning and a reasoning summary), tool call and result, delegation, refusal, and final report.

**Token guardrails:** each ticket has a 150k-token / 40-request / 80-tool-call budget shared by the whole team. When it runs out, the run pauses, a budget-extension request is filed, and a human must approve before work continues. Delegation is capped at depth 3 and 8 per ticket, and model responses are capped at 4k output tokens.

**Docs:**
- `output/harness.md`: agents table, loop and delegation design, audit format, full 20-tool table tied to tickets, and a Safety section covering money, drafts, least privilege, data integrity, token limits, and secrets.
- `mcp_server/README.md`: rewritten for all 20 tools.
- New `README.md` and `scripts/reset_db.py`; `requirements.txt` updated.

**Tested:**
- All MCP guardrails on a scratch database: below-cost price, blocked-vendor PO, insufficient funds, agent-as-approver, duplicates, and early "resolved" were all refused.
- A live full run with gpt-6-luna on a scratch copy. 101: invoice 501 payment request and a customer draft. 102: rent request (Facilities delegated to Accounting). 103: $49.50 price override, 12-unit PO, and quote draft. The Boss flagged that the $264 PO is $104 short of cash once the other requests are approved. All tickets ended in `waiting_approval`.
- `data/campus_customs.db` and `data/campus_customs_new.db` were not modified, and the real audit trail will start on the first real run.

## User prompt

```text
Start a new session so you are able to call the tools, but you don't need to call them yet
```

## Assistant response

Checked this session's MCP status: `campus-customs` is still connected with the original 3 tools, because the server process predates the Problem 5 changes. I have no tool that can start a new session, and Claude Code only lets the user reconnect `.mcp.json` servers. Asked the user to either reconnect `campus-customs` from `/mcp` in this session or open a new Code session in `Homework/hw5`. Either way it reloads `server.py` with all 20 tools. As requested, no tools were called.

# Problem 6: Plan the three tickets

## User prompt

```text
Problem 6: Plan the three tickets
Before you wire the backend, I will explain what I expect the team to do when they work on each open ticket (not instructions, just my predictions). Create a simple page called output/desk_tickets.html that has one tab per ticket (101-103) that I can open and edit to explain my thinking. Also add two more tabs to this page called "Cash" and "Reflection" - leave these tabs blank with "coming later" for now.

In each ticket tab, I'll write my thoughts in an "Expected" section. Leave room on each tab for an "Actual" section that will be filled after the agents run.

Note: I do not want the boss to assign all agents to all tickets. For efficiency, I want each agent to delegate each ticket to 1-2 agents so work can be completed incrementally in a logical sequence (rather than all agents working in parallel on everything simultaneously)
```

## Assistant response

**Desk page:** created `output/desk_tickets.html`, a self-contained page with no external files.
- Tabs: Ticket 101, Ticket 102, Ticket 103, Cash, and Reflection. Cash and Reflection say "Coming later".
- Each ticket tab shows the ticket's facts from the database, an editable **Expected** box, and an **Actual** box marked "To be filled in after the agents run". I left Expected blank for your predictions.
- Edits autosave in the browser. A "Download page with my edits" button saves a copy with the text written into the HTML; the text can also be typed directly into the marked `<div>`s.
- Verified in the browser: tabs switch, editing autosaves, no console errors. Added an `hw5-desk-pages` static-server entry to the class `.claude/launch.json` for previewing.

**Delegation changed to 1–2 agents, in sequence:**
- Code: each agent may delegate to at most 2 different agents per ticket (a third is refused), `delegate_task` is `sequential=True`, and the per-ticket cap is now 6.
- Prompts: `boss.md` routing is now a step plan. Customer order goes to Inventory, then Customer Service. Rent goes to Facilities, which brings in Accounting. Price override goes to Accounting (which brings in Inventory), then Customer Service. `shop_rules.md` tells every agent to delegate sparingly and in sequence.
- Tested offline with no model calls: Boss's third delegate, repeat tasks, and delegating back up the chain were refused.
- `output/harness.md` updated (safety limits table plus a Problem 6 section).

## User prompt (follow-up)

```text
Returning to Problem 6 briefly - I manually added my expectations to output/desk_tickets.html. I want the text to appear in the box like it's my reported guess, not just placeholder text that can be overwritten by any user. I think tickets 101 and 102 look roughly right, but 103 has "faded" text that looks like it's meant to be overwritten. Please correct this visually, preserving what I wrote as a guess for each ticket
```

## Assistant response

All three predictions were stored in the boxes' `data-placeholder` attribute. That attribute is shown as faded hint text and disappears as soon as someone types in the box. Converted each one into fixed, read-only text:
- A `<blockquote class="guess">` in normal ink color with a gold accent bar.
- Labeled "My prediction (recorded before the agents ran)".

The wording was copied verbatim, and a script confirmed that all three texts match the originals character for character. Because there are no editable boxes left, I removed the editing toolbar and the browser-autosave script; the tabs still work. The Actual sections are unchanged ("To be filled in after the agents run"). Checked in the browser: the text is not editable, renders in the normal dark color, and there are no console errors.

Also added `hw5/.claude/launch.json` (desk-page and backend preview entries), because this session now runs from `hw5`.

# Problem 7: Backend routes

## User prompt

```text
Problem 7: Backend routes
Our React frontend dashboard (which will be created shortly) will need a beckend for calls. Use FastAPI to add routes in backend/main.py. The routes will do the following things:

* Return the three tickets and explain whether each is resolved or remains open
* Receive a ticket id and run the agent team on that ticket
* Return recent agent events (what was said and which tools the agent called) so the dashboard can refresh and be monitored by a human
* Approve payments or purchases AFTER a human clicks approve on the frontend (agents should only draft/prepare these actions until they are human-approved)
* Return the current checking balance from cash_accounts
* Reset the working database to the original values so we can refresh the working database for future tries/runs


In the backend/ folder, the server should start with the following command:
uvicorn main:app --reload --port 8000

Update output/harness.md to list each route and explain what it does (use only one line per route explanation)
```

## Assistant response

Created `backend/main.py` (FastAPI). It starts from `backend/` with `uvicorn main:app --reload --port 8000`; it adds `hw5` to the import path so `main:app` works from that folder. All reads and writes go through the shared MCP connection, and agents still never get the approve/reject tools.

**Routes:**
- `GET /api/tickets` and `/api/tickets/{id}`: tickets with `is_resolved` and a one-line explanation.
- `POST /api/tickets/{id}/run`: background agent run that returns a `run_id`. Only one run at a time; 409 if busy.
- `GET /api/runs`, `/api/runs/{id}`: run status and the Boss's decision.
- `GET /api/events`: audit-trail events with a readable `summary` and a `seq` cursor for polling.
- `GET /api/approvals`, plus `POST .../approve` and `POST .../reject`: human decisions, logged as `human_decision` audit events. Refusals return 409; unknown ids return 404.
- `GET /api/cash`: checking balance plus pending cash requests.
- `POST /api/reset`: requires `confirm: true`; refused during a run.
- `GET /api/health`.

The agents now load the model only when a ticket runs, so read and approval routes work even without the Portkey key.

**Tested on a scratch database copy (port 8001):**
- A live gpt-6-luna run of ticket 103 delegated in sequence, Boss → Accounting → Inventory, and filed PO #1 and price override #2.
- A second run and a reset during the run both returned 409.
- Approving the PO was refused (vendor blocked by invoice 501). Approving as "accounting" was refused. The price override was approved and the PO rejected.
- Approving a payment for invoice 501 dropped checking from $3,400 to $2,560 and marked the invoice paid. Reset restored $3,400 and all tickets reopened.
- Fixed two issues found in testing: refused approvals now read clearly in the event log, and unknown ids return 404.

Updated `output/harness.md` (one line per route) and `README.md`, and added an `hw5-backend` entry to the class `.claude/launch.json`. The real databases were not modified.

# Problem 8: Agent dashboard

## User prompt

```text
Problem 8: Agent dashboard
Now, make the frontend dashboard in the frontend/ folder using React, Vite, and TypeScript. The page should call routes you made in Problem 7. The dashboard has several minimum requirements:

* List all three tickets
* Let a human select a single ticket to start agent work on it
* Show all agents and what they are saying/thinking/doing during the ticket run (like a live view for the human to monitor how they work in real time) - these updates should be brief, but generally comprehensive of major decisions. The point is to monitor all major actions, but not to overuse tokens overly explaining everything
* Mark the ticket as resolved when the run is complete
* Summarize BRIEFLY what each agent did on that ticket (replacing the "live feed" with one summary afterwards)
* Ask for human approval for ANY payment or purchase decision BEFORE money is sent
* Show live checking account balance (that dynamically updates as transactions actually happen)


Make the dashboard clean and minimalistic. The design should be user-friendly so a manager will not mind monitoring the dashboard. Add some Handsome Dan-themed styling to make the dashboard Yale theme.

The frontend should connect to the backend at http://localhost:8000. The backend should allow the Vite page origin (usually http://localhost:5173) so the browser can call those routes.

The dashboard should start with the command "npm run dev" which opens the React desk in my browser.

Create output/design.md that explains how you chose the dashboard design specs. Touch on the layout, how resolved tickets show up, live cash balance, and how agents give live updates.
```

## Assistant response

**Frontend:** built `frontend/` (React 19 + Vite 8 + TypeScript, same versions as hw4). `npm run dev` serves port 5173 and opens the browser, and the app calls `http://localhost:8000` directly (override with `VITE_API_URL`).
- **Layout:** three columns.
  - Ticket list with status pills.
  - Selected ticket with a single **Start agent work** button.
  - A sticky **Needs your OK** approval queue.
- **Header:** a live checking balance that polls every 2 s and flashes with the delta (for example "−$840.00 just now") only when money actually moves.
- **Live view:** one lane per agent (Working / Waiting on X / Done, plus its latest line) and a feed of major steps only: reasoning sentences, delegations, write actions, refusals, and conclusions. It reads the existing audit trail, so monitoring uses no extra tokens.
- **After a run:** a brief per-agent summary replaces the feed (path, actions, checks, conclusion).
- **Approvals:** money requests show the balance impact and warnings, and need a second "Yes, pay" click. Rejects need a reason. Drafts show "will not be sent".
- **Yale styling:** Yale blue, serif headings and figures, an original Handsome Dan bulldog badge, the Boss shown as Handsome Dan, and light 🐾 / "Boola Boola" touches.

**Backend additions:**
- `GET /api/runs/{id}/summary`, built from the audit trail.
- `last_run` on tickets.
- Brief `summary` and `importance` fields on events.
- An explicit CORS allowance for `http://localhost:5173`.
- **Auto-resolve:** the ticket becomes Resolved right after the run if nothing needs approval, otherwise right after the human decides its last pending request. This keeps money decisions visible instead of closing tickets with payments outstanding.
- The MCP `set_ticket_status` now accepts the backend's `system` identity for this.

**Tested end to end** in the browser against a scratch database:
- Ran ticket 101 live. The lanes showed Boss "Waiting on Inventory" and Inventory working; the run went Boss → Inventory → Accounting and requested the $840 invoice payment.
- The summary replaced the feed. Approve → "Yes, pay" took checking from $3,400 to $2,560 with the flash, and ticket 101 turned ✓ Resolved.
- Reset restored $3,400 and reopened all tickets.
- Fixed the issues found: the summary now credits every delegator, the resolved line is clean, and the summary view handles older data shapes without crashing.
- `tsc` and `oxlint` are clean, and the real databases were not modified.

Wrote `output/design.md` (layout, resolved tickets, live cash, live agent updates, approvals, Yale styling) and updated `output/harness.md` and `README.md`.

# Problem 9: Resolve the tickets

## User prompt

```text
Problem 9: Resolve the tickets
Before we test the agents, please reset the working database (data/campus_customs_new.db) so we can start fresh. Confirm the values match the originals that we saved a copy of, especially checking balance. Please run the dashboard so we can resolve the three tickets live
```

## Assistant response

**Reset:** ran `scripts/reset_db.py`, which logged a `db_reset` entry as the first line of the real `output/audit_trail.json`, and verified the result against `campus_customs.db`:
- Identical SHA-1 (`f447ca6a…`).
- Identical table list; all 9 tables match row for row.
- Checking balance $3,400.00 as of 2026-08-31 in both files.
- Desk date 2026-08-31; invoice 501 is $840 open, due 2026-08-28; lease 1 is $2,400 due 2026-09-02.
- Tickets 101–103 open, 0 payments.

**Servers:** started the backend (port 8000) and the dashboard (port 5173) from `hw5/.claude/launch.json`. The backend has no `CAMPUS_DB_PATH` or `AUDIT_TRAIL_PATH` overrides, so it uses the real working copy and audit trail. Starting the `uvicorn` script directly was blocked by macOS ("Operation not permitted"), so the launch entry now runs `.venv/bin/python -m uvicorn` (same server, same port). The dashboard shows $3,400.00 and three open tickets, ready for the live runs.

## User prompt (follow-up)

```text
Ticket 103 ran into an issue where an unpaid invoice is required to ship additional units of the product. I tried approving the bill to order more units, but I kept getting denied because the of the outstanding invoice. The agents should be able to pull up that other pending invoice so I can approve it. Ticket 101 seems to have a similar issue
```

## Assistant response

**Cause (from the audit trail):** no agent ever filed a payment request for invoice 501, so there was nothing to approve. On both tickets Accounting compared the $840 invoice with "cash after all pending requests" ($1,000 − the $264 PO = $736) and decided it was "$104 short". But that PO can't be approved until invoice 501 is paid, so it never competed with the invoice. On ticket 101, Inventory's hand-off also told Accounting "do not … create a payment".

**Fixes:**
- **MCP tools:**
  - The funds check excludes a vendor's dependent POs when paying that vendor's invoice.
  - `draft_purchase_order` returns `must_pay_first`, listing each blocking invoice and whether it has a payment request.
  - Blocked-vendor refusals name the invoice and its request.
  - `get_cash_balance` itemizes pending requests.
- **Prompts:**
  - Accounting must always file the payment request for a blocking invoice; only the real balance can stop it.
  - The Boss verifies that every blocking invoice has a payment request before setting `waiting_approval`.
  - Inventory asks Accounting to file it and never says not to.
- **Dashboard:** payments are listed before POs, and each PO card shows its live blocker ("Approve payment request #4 first", or "no payment request yet").

**Result:** re-ran ticket 101 (Boss → Inventory → Accounting, plus Customer Service). Accounting filed **payment #4 for invoice 501 ($840)** and Customer Service drafted #5 to Tauhid Zaman (not sent). The PO card now pointed to #4. The user approved #4: invoice 501 is paid, checking is $1,000 → $160, and Bulldog Print Co is unblocked.

**Still open:**
- PO #2 ($264, ticket 103) is no longer blocked by the vendor, but it exceeds the $160 balance, so it will be refused under the no-negative-balance rule.
- Draft #5 (ticket 101) awaits review.

## User prompt (wrap-up)

```text
I started an itemized log of how money flowed in outputs/desk_ticket.html. Please complete the log with actions by ticket, and be sure to confirm that the ending balance in this ledger matches the ending balance in the working database and the live dashboard.

Also, save files called:

* output/resolved_tickets.json (fields for each ticket: id, final status, summarized outcome, what each agent did, and all human approvals)
* output/resolved_board.html (a page that can run locally with a screenshot of each resolved ticket (101, 102, and 103). Since 103 cannot be fully resolved, screenshot the dashboard AS IS (do not make up information or magically resolve 103)


Append these agent / ticket runs in output/audit_trail.json. And complete output/harness.md such that it explains all tables, MCP tools, agents, API routes, dashboard functionality, and safety rules
```

## Assistant response

**Cash log** (Cash tab of `output/desk_tickets.html`, the file the prompt calls `outputs/desk_ticket.html`):
- Kept the user's ticket 102 line verbatim under "My entry".
- Added labeled entries for 101 and 103.
- Added an itemized table by ticket: opening $3,400 → rent −$2,400 (#1, payment #1) → $1,000 → invoice 501 −$840 (#4, payment #2) → $160. The $0 actions are listed too: price override #3, draft #5 (not sent), and PO #2 pending with 6 refused approvals.
- Reconciliation: ledger **$160.00** = `cash_accounts` in `campus_customs_new.db` **$160.00** = live dashboard / `GET /api/cash` **$160.00**.

**`output/resolved_tickets.json`:** generated by `scripts/build_resolution_report.py` from the API, the working DB (read-only), the original DB, and the audit trail. No values are typed in by hand. For each ticket it records id, final status, summarized outcome, what each agent did (per run), all human approvals (including every refused attempt), and payments. It also contains the cash ledger and reconciliation. 101 and 102 are resolved; 103 is `waiting_approval`.

**`output/resolved_board.html`:** a self-contained page with screenshots embedded as base64. `scripts/capture_board.py` captured the live dashboard at 1440 px through Playwright and the installed Chrome. Ticket 103 is shown as is: "Run complete · needs you", with PO #2 marked "Not enough cash". (The preview tool's screenshots were capped at about 800×600, too small for full-page captures.)

**Audit trail:** confirmed that all 5 runs (102; 103 ×2; 101 ×2) and every human decision were already appended live. Appended one `report_generated` entry with the reconciliation; the earlier content was unchanged. Also: human-decision entries now include `ticket_id`.

**`output/harness.md`:** kept the Problem 2–3 sections and added the `approval_requests` table. Replaced the per-problem patchwork with one consolidated final reference: agents, all 20 MCP tools, all 13 routes, dashboard functionality, audit trail, safety rules with current limits, live results, and a change history.

# Problem 10: Reflection

## User prompt

```text
Problem 10: Reflection
In output/desk_tickets.html, please fill out the reflection tab body with my own words below.

Ticket 101:

* The agents did the right thing, for now, but there is no mechanism making sure they circle back when invoice 501's stock is delivered. C+
* Actual performance was generally what I expected, although I did not predict the stockout issue. I think the actual run went roughly how I expected and how I'd like it to.


Ticket 102:

* The agents handled this (simple) ticket perfectly. A+
* Actual performance was what I expected, and I have no improvement notes for the agents.


Ticket 103:

* After fixing the invoice 501 issue (I initially couldn't approve the invoice because it wasn't a part of the original ticket), the agents asked for the appropriate approvals. However, the order could not be fulfilled immediately because there was insufficient cash to order additional hoodies. I would have liked the agents to draft a Customer Service message explaining how we'd like to complete the order, but are pending an upcoming shipment (buying time for revenue to give us the cash to actually place said order). B+
* Without knowing the stock shortage issues were going to pop up, the agents generally did what I expected.


Overall:

* One agent would have been simpler, but more expensive, to implement. I think part of the issues my agents had were gaps in communication. For example, the agents didn't know how to ask a human to approve invoice 501 at first. They were rejecting other approvals because they knew 501 was required, but there was nothing asking the human to approve 501.
* Campus Customs can now handle lots of simple tasks that could have come up. For example:
   * Identify which vendor(s) is best to restock all out-of-stock items
   * Identify unpaid invoices and prioritize which need to be paid first
   * Send Customer Service emails apologizing for delay (if a customer circled back after not having their order addressed immediately)
* Campus Customs probably could not handle all potential problems, such as:
   * Identify priority items for potential discount sales (to offload stale inventory)
   * Determine which suppliers are best to work with
   * Identify new designs for items in the upcoming season
```

## Assistant response

Replaced "Coming later" in the Reflection tab of `output/desk_tickets.html` with the user's reflection, word for word, under the headings Ticket 101, Ticket 102, Ticket 103, and Overall. The bullets and the nested sub-bullets are kept as written. The only formatting added: each letter grade (C+, A+, B+) is shown as a small Yale-blue badge, with the wording unchanged. A script confirmed that every sentence appears verbatim. Checked in the browser: the tab renders correctly with no console errors. No other tabs were changed.

# Problem 11: Submit to GitHub

## User prompt

```text
Problem 11: Submit to GitHub
Push all of our code to a public GitHub repository so it can be cloned and graded. Please save the repo url in output/github_url.txt

Remember not to push any API keys or env files, just use samples with instructions, per AI guidelines in the root.

Do push both database files in the data folder (original and working copy). README file should explain how to copy the original database to the working copy when reseting a run and how to start the MCP server, FastAPI backend, React dashboard.

I have included the expected file layout as a screenshot. Please move files to match the expectation as needed
```

(The user attached a screenshot of the expected `hw5/` file tree.)

## Assistant response

**Layout:** matched the expected tree. Added `.env.example` (a placeholder key with copy instructions), `.gitignore`, and `output/github_url.txt`; every other expected file was already in place. Supporting files beyond the tree were kept: `backend/agents/`, `team.py`, the other backend modules, `prompts/shop_rules.md`, `scripts/`, and `output/screenshots/`. `stock_regression/` is a separate project that happens to live in `hw5`; it was left in place and git-ignored, not pushed.

**Portability:**
- `.mcp.json` now uses paths relative to `hw5/` (it previously had absolute paths containing the username), and the backend resolves them against `hw5/`. Tested from inside `backend/`: 20 tools, balance $160.
- The key is read from `hw5/.env`. The missing-key error now points to `.env.example`.

**Secrets:**
- `.gitignore` excludes `.env`, `*.env`, `Portkey.env`, `.venv/`, `node_modules/`, `.claude/`, and caches.
- A scan compared all 72 staged files against the real Portkey key (only a yes/no result was printed) and against common secret patterns. No matches, and no absolute home paths.

**Database files:** both `.db` files are committed. The working copy shows the end-of-run state ($160).

**README:** rewritten with setup, `.env`, two ways to reset (`scripts/reset_db.py`, or copying `campus_customs.db` over `campus_customs_new.db`), and how to start the MCP server, FastAPI backend, and dashboard.

**Pushed** to the public repo https://github.com/tom-barbaro-som/mgt409-hw5. The URL is saved in `output/github_url.txt`.

**Follow-up:** a fresh clone of the repo was verified (all expected files present; MCP smoke 4/4 passing from the relative `.mcp.json`). `scripts/mcp_smoke.py` now writes `output/mcp_smoke_rerun.json` instead of overwriting the Problem 4 evidence in `output/mcp_smoke.json`.
