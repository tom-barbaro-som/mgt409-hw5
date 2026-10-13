# Campus Customs: Multi-Agent Operations (MGT 409 · Homework 5)

Campus Customs is a New Haven store that sells Yale merchandise. This repo is its AI operations team:

- **MCP server** (`mcp_server/`, FastMCP): the only layer that reads or writes shop data. It has 20 tools.
- **Agent team** (`backend/`, PydanticAI on `gpt-6-luna` via Portkey): Boss, Inventory, Accounting, Facilities, and Customer Service. They delegate to each other (1–2 teammates per agent, one at a time).
- **FastAPI backend** (`backend/main.py`): routes the dashboard uses to list tickets, run the agents, stream events, approve or reject requests, read cash, and reset the data.
- **React dashboard** (`frontend/`, Vite + TypeScript): a manager watches the agents live and approves every payment.

Agents only **draft and request**. Nothing is paid, ordered, or discounted until a human approves it on the dashboard, and messages are **never sent**. Full documentation is in [`output/harness.md`](output/harness.md); the dashboard design is in [`output/design.md`](output/design.md).

## Layout

```
hw5/
├── AI_prompts.md            full prompt/response log for the assignment
├── requirements.txt         Python dependencies
├── .env.example             template for your Portkey key (copy to .env)
├── .mcp.json                MCP connection (used by Claude Code and the backend)
├── data/
│   ├── campus_customs.db        ORIGINAL database: never modified
│   └── campus_customs_new.db    WORKING copy: everything reads/writes here
├── mcp_server/              server.py (20 tools) + README.md
├── backend/                 main.py (FastAPI), models.py, prompts/ (one per agent + shared shop_rules.md),
│                            agents/ (one file per agent), team.py (agent loop), config.py, audit.py, ...
├── frontend/                React + Vite + TypeScript dashboard
├── scripts/                 reset_db.py, mcp_smoke.py, capture_board.py, build_resolution_report.py
└── output/                  harness.md, design.md, mcp_smoke.json, desk_tickets.html, resolved_tickets.json,
                             resolved_board.html (+ screenshots/), audit_trail.json, github_url.txt
```

## 1. Setup (once)

Requires Python 3.12+ and Node 20+. Run from this `hw5/` folder:

```bash
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                 # then edit .env and set PORTKEY_API_KEY
cd frontend && npm install && cd ..
```

The key is read from `.env` (git-ignored) and is never printed or logged. Only `gpt-6-luna` is allowed. Viewing the dashboard, approving requests, and resetting all work without a key; only running the agents needs one.

## 2. Reset the working database (before every fresh run)

The working copy `data/campus_customs_new.db` holds every change (payments, drafts, statuses). To start over, copy the untouched original over it. Use either:

```bash
python scripts/reset_db.py                               # copies, verifies the checksum, logs it in the audit trail
```

```bash
cp data/campus_customs.db data/campus_customs_new.db     # plain copy (do this while the backend is stopped)
```

You can also click **Reset demo data** in the dashboard footer, or `POST /api/reset` with `{"confirm": true}`. A reset restores checking to **$3,400.00** and reopens tickets 101–103. The audit trail is append-only and is never erased by a reset.

> The committed working copy reflects the end of the graded live run: checking $160.00, tickets 101 and 102 resolved, and 103 waiting on a $264 order that cash can't cover. Reset first if you want to run the tickets yourself.

## 3. Start the MCP server

The backend starts the MCP server for you (over stdio, from `.mcp.json`), so you normally don't run it by hand. To run or inspect it on its own:

```bash
python mcp_server/server.py          # stdio MCP server on the working DB
python scripts/mcp_smoke.py          # calls tools via .mcp.json, checks them against the DB → output/mcp_smoke_rerun.json
```

In **Claude Code**, open this folder and approve the `campus-customs` server from `.mcp.json`; its 20 tools then appear in the session. Details are in [`mcp_server/README.md`](mcp_server/README.md).

## 4. Start the FastAPI backend (terminal 1)

```bash
cd backend
uvicorn main:app --reload --port 8000        # venv active; API docs at http://localhost:8000/docs
```

All routes are listed in `output/harness.md` under "Backend API routes". CORS allows the dashboard at `http://localhost:5173`.

## 5. Start the React dashboard (terminal 2)

```bash
cd frontend
npm run dev                                  # opens http://localhost:5173 in your browser
```

It connects to `http://localhost:8000`; set `VITE_API_URL` to use a different address. In the dashboard:
1. Enter your name under **Approving as**.
2. Pick a ticket and click **Start agent work**.
3. Watch the live agent lanes. When the run finishes, a summary replaces the live feed.
4. Approve or reject the requests in **Needs your OK**. Money needs a second **Yes, pay** click.

The checking balance in the header updates as payments actually post.

## Other commands

```bash
python -m backend.run_tickets --ticket 102   # run one ticket from the command line (no dashboard)
python -m backend.run_tickets --all          # reset the DB, then run every open ticket
python scripts/capture_board.py              # screenshot each ticket on the live dashboard (uses installed Chrome)
python scripts/build_resolution_report.py    # rebuild resolved_tickets.json, resolved_board.html, cash reconciliation
```

## Safety, in brief
- Only a human can approve. Approval is the only path for money. The pay tool refuses a negative balance and refuses orders to a vendor with an unpaid invoice.
- There is no external contact of any kind. Drafts are stored with `sent: false`.
- Each agent sees only its role's tools, and its identity is stamped by the backend.
- Token and loop limits apply per ticket (150k tokens, 40 model requests, 6 delegations). When a ticket hits its budget, the work pauses until a human approves more.
- Every step is recorded in the append-only `output/audit_trail.json`.
