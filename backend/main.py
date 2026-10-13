"""FastAPI backend for the Campus Customs operations dashboard.

Start from the backend/ folder (with the hw5 venv active):
    uvicorn main:app --reload --port 8000

Every shop read/write goes through the MCP server (via the team's shared MCP
connection). Agents only draft and request; the approve/reject routes are the
human's button clicks and are the only way money moves.
"""

from __future__ import annotations

import asyncio
import re
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# `uvicorn main:app` runs from backend/, so make the hw5 folder importable as a package root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException, Query  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from backend.audit import read_audit_trail  # noqa: E402
from backend.run_summary import TOOL_LABELS, brief, describe_write, summarize_run  # noqa: E402
from backend.config import AUDIT_TRAIL_PATH, AgentNotConfiguredError, build_model  # noqa: E402
from backend.db_reset import reset_working_db  # noqa: E402
from backend.models import ApproveBody, RejectBody, ResetBody, RunJob  # noqa: E402
from backend.team import OperationsTeam  # noqa: E402

RECENT_EVENTS_DEFAULT = 100


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class State:
    team: OperationsTeam
    jobs: dict[str, RunJob] = {}
    tasks: dict[str, asyncio.Task] = {}

    @classmethod
    def running(cls) -> list[RunJob]:
        return [j for j in cls.jobs.values() if j.status == "running"]


@asynccontextmanager
async def lifespan(_: FastAPI):
    State.team = OperationsTeam()
    async with State.team:  # one MCP connection for the whole server
        yield
    for task in State.tasks.values():
        task.cancel()


app = FastAPI(title="Campus Customs Operations API", version="1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # Vite dashboard
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",  # other local ports only
    allow_methods=["*"],
    allow_headers=["*"],
)


async def shop(tool: str, **args: Any) -> Any:
    """System/human call to an MCP tool (agents use their own guarded path)."""
    return await State.team.call_shop_tool(tool, args)


# --------------------------------------------------------------------------- #
# Tickets
# --------------------------------------------------------------------------- #
def _explain(ticket: dict, approvals: list[dict]) -> str:
    status = ticket["status"]
    pending = [a for a in approvals if a["status"] == "pending"]
    last_note = (ticket.get("notes") or "").strip().splitlines()[-1:] or [""]
    if status == "resolved":
        note = re.sub(r"^\[[^\]]*\]\s*(status \S+ -> \S+:\s*)?", "", last_note[0])
        return f"Resolved. {note}".strip()
    if pending:
        items = "; ".join(
            f"#{a['id']} {a['kind'].replace('_', ' ')}" + (f" ${a['amount']:,.2f}" if a["amount"] else "")
            for a in pending
        )
        return f"Open ({status}): waiting on {len(pending)} human approval(s): {items}."
    if status == "open" and not approvals:
        return "Open: not yet worked by the agent team."
    if approvals:
        decided = "; ".join(f"#{a['id']} {a['kind'].replace('_', ' ')} {a['status']}" for a in approvals)
        return f"Open ({status}): all requests decided ({decided}). Run the agents again to finish the ticket."
    labels = {"blocked": "Blocked", "in_progress": "In progress", "waiting_approval": "Waiting", "open": "Open"}
    return f"{labels.get(status, status)}: {last_note[0]}".strip()


def _last_run(ticket_id: int) -> dict | None:
    """Most recent agent run for a ticket, rebuilt from the audit trail (survives restarts)."""
    last: dict | None = None
    for e in read_audit_trail(AUDIT_TRAIL_PATH):
        if e.get("ticket_id") != ticket_id:
            continue
        if e["event"] == "ticket_run_started":
            last = {"run_id": e["run_id"], "status": "running", "started_at": e["ts"], "finished_at": None}
        elif e["event"] == "ticket_run_finished" and last and e.get("run_id") == last["run_id"]:
            last.update(status=e["detail"].get("outcome", "completed"), finished_at=e["ts"])
    if last and last["status"] == "running" and not any(j.run_id == last["run_id"] for j in State.running()):
        last["status"] = "interrupted"  # server restarted mid-run
    return last


async def _auto_resolve(ticket_id: int | None, why: str) -> bool:
    """Close a ticket once the agents finished and no request still waits on the human."""
    if ticket_id is None:
        return False
    data = await shop("get_ticket", ticket_id=ticket_id)
    if not data.get("found") or data["ticket"]["status"] != "waiting_approval":
        return False
    if any(a["status"] == "pending" for a in data["approval_requests"]):
        return False
    result = await shop("set_ticket_status", ticket_id=ticket_id, status="resolved", reason=why, agent="system")
    if result.get("ok"):
        State.team.audit.append("ticket_resolved", ticket_id=ticket_id, agent="system", reasoning=why)
    return bool(result.get("ok"))


async def _ticket_view(ticket_id: int) -> dict:
    data = await shop("get_ticket", ticket_id=ticket_id)
    if not data.get("found"):
        raise HTTPException(404, data.get("error", "Ticket not found"))
    t, approvals = data["ticket"], data["approval_requests"]
    running = next((j.run_id for j in State.running() if j.ticket_id == ticket_id), None)
    last_run = _last_run(ticket_id)
    return {
        **t,
        "is_resolved": t["status"] == "resolved",
        "explanation": _explain(t, approvals),
        "approval_requests": approvals,
        "linked": data["linked"],
        "agent_run_in_progress": running,
        "last_run": last_run,
    }


@app.get("/api/tickets")
async def list_tickets() -> dict:
    """All tickets with resolved/open status and a one-line explanation."""
    data = await shop("list_tickets", status=None)
    tickets = [await _ticket_view(t["id"]) for t in data["tickets"]]
    return {
        "desk_date_today": data["desk_date_today"],
        "resolved": sum(t["is_resolved"] for t in tickets),
        "open": sum(not t["is_resolved"] for t in tickets),
        "tickets": tickets,
    }


@app.get("/api/tickets/{ticket_id}")
async def get_ticket(ticket_id: int) -> dict:
    return await _ticket_view(ticket_id)


# --------------------------------------------------------------------------- #
# Agent runs
# --------------------------------------------------------------------------- #
async def _run_job(job: RunJob) -> None:
    try:
        job.result = await State.team.run_ticket(job.ticket_id, run_id=job.run_id)
        job.status = job.result.outcome
        if job.status == "completed":
            await _auto_resolve(job.ticket_id, "Agent run complete and nothing awaits human approval.")
    except Exception as exc:  # run_ticket already audits; this is a last-resort guard
        job.status = "error"
        State.team.audit.append("error", run_id=job.run_id, ticket_id=job.ticket_id, agent="system",
                                detail={"error": f"{type(exc).__name__}: {exc}"})
    finally:
        job.finished_at = _now()
        State.tasks.pop(job.run_id, None)


@app.post("/api/tickets/{ticket_id}/run", status_code=202)
async def run_ticket(ticket_id: int) -> RunJob:
    """Start the agent team on one ticket in the background; poll /api/runs/{run_id} and /api/events."""
    await _ticket_view(ticket_id)  # 404 if the ticket does not exist
    if State.running():
        busy = State.running()[0]
        raise HTTPException(409, f"Agents are already working on ticket {busy.ticket_id} ({busy.run_id}). "
                                 "One run at a time keeps cash decisions consistent.")
    try:
        build_model()  # fail fast if the Portkey key or model is missing
    except AgentNotConfiguredError as exc:
        raise HTTPException(503, str(exc)) from exc
    job = RunJob(run_id=OperationsTeam.new_run_id(ticket_id), ticket_id=ticket_id, status="running", started_at=_now())
    State.jobs[job.run_id] = job
    State.tasks[job.run_id] = asyncio.create_task(_run_job(job))
    return job


@app.get("/api/runs")
async def list_runs() -> dict:
    return {"runs": sorted(State.jobs.values(), key=lambda j: j.started_at, reverse=True)}


@app.get("/api/runs/{run_id}/summary")
async def run_summary(run_id: str) -> dict:
    """Brief per-agent summary of a finished run, built from the audit trail (no model calls)."""
    entries = read_audit_trail(AUDIT_TRAIL_PATH, run_id=run_id)
    if not entries:
        raise HTTPException(404, f"No audit entries for run {run_id}.")
    return summarize_run(entries)


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str) -> RunJob:
    if run_id not in State.jobs:
        raise HTTPException(404, f"Unknown run {run_id} (runs are kept in memory until the server restarts).")
    return State.jobs[run_id]


# --------------------------------------------------------------------------- #
# Agent events (audit trail)
# --------------------------------------------------------------------------- #
WRITE_TOOLS = {"add_ticket_note", "set_ticket_status", "request_payment", "draft_purchase_order",
               "request_price_override", "draft_message"}
MINOR_EVENTS = {"agent_started", "tool_call", "tool_result"}


def _summarize(e: dict) -> str:
    """One short, human-readable line per event (no model calls)."""
    d, who, ev = e.get("detail", {}), e.get("agent", "system"), e["event"]
    if ev == "model_step":
        return brief(e.get("reasoning"), 160) or "thinking…"
    if ev == "tool_call":
        return TOOL_LABELS.get(d.get("tool"), d.get("tool", "").replace("_", " "))
    if ev == "tool_result":
        res = d.get("result")
        return describe_write(d.get("tool"), {}, res) or (
            f"{d.get('tool')}: refused" if isinstance(res, dict) and res.get("ok") is False else
            f"{TOOL_LABELS.get(d.get('tool'), d.get('tool'))} ✓")
    if ev == "delegation":
        return f"asked {d.get('to_agent')}: {brief(d.get('task'), 140)}"
    if ev == "delegation_refused":
        return f"delegation to {d.get('to_agent')} refused: {brief(d.get('error'), 120)}"
    if ev == "tool_blocked":
        return f"blocked from {d.get('tool')}"
    if ev == "agent_started":
        return "started"
    if ev == "agent_finished":
        out = d.get("output", {})
        return "done: " + brief(out.get("decision") or out.get("recommendation") or e.get("reasoning"), 180)
    if ev == "human_decision":
        return f"{d.get('by')}: request #{d.get('approval_id')} {d.get('decision')} ({brief(str(d.get('result_summary', '')), 120)})"
    if ev == "ticket_run_started":
        return "run started"
    if ev == "ticket_run_finished":
        return f"run finished ({d.get('outcome')})"
    if ev == "ticket_resolved":
        return f"ticket resolved: {e.get('reasoning', '')}"
    return f"{ev.replace('_', ' ')}: {brief(e.get('reasoning') or str(d), 140)}"


def _importance(e: dict) -> str:
    if e["event"] == "tool_result":
        res = e.get("detail", {}).get("result")
        refused = isinstance(res, dict) and res.get("ok") is False
        return "major" if refused or e["detail"].get("tool") in WRITE_TOOLS else "minor"
    return "minor" if e["event"] in MINOR_EVENTS else "major"


@app.get("/api/events")
async def recent_events(
    after: int | None = Query(None, description="Return events with seq greater than this (for polling)."),
    limit: int = Query(RECENT_EVENTS_DEFAULT, ge=1, le=1000),
    ticket_id: int | None = None,
    run_id: str | None = None,
    include_tool_results: bool = True,
) -> dict:
    """Recent agent events: what each agent said and which tools it called (newest last)."""
    entries = read_audit_trail(AUDIT_TRAIL_PATH)
    events = []
    for seq, e in enumerate(entries, start=1):
        if after is not None and seq <= after:
            continue
        if ticket_id is not None and e.get("ticket_id") != ticket_id:
            continue
        if run_id is not None and e.get("run_id") != run_id:
            continue
        if not include_tool_results and e["event"] == "tool_result":
            continue
        events.append({"seq": seq, **e, "summary": _summarize(e), "importance": _importance(e)})
    return {"last_seq": len(entries), "count": len(events[-limit:]), "events": events[-limit:]}


# --------------------------------------------------------------------------- #
# Human approvals (the only way money moves)
# --------------------------------------------------------------------------- #
@app.get("/api/approvals")
async def list_approvals(status: str | None = "pending", ticket_id: int | None = None, kind: str | None = None) -> dict:
    """Approval queue; purchase orders carry their live blocking invoices (and the payment request for each)."""
    data = await shop("list_approval_requests", status=status, ticket_id=ticket_id, kind=kind)
    if any(r["kind"] == "purchase_order" for r in data["requests"]):
        vendors = {v["id"]: v for v in (await shop("list_vendors"))["vendors"]}
        payments = [r for r in (await shop("list_approval_requests", status=None, kind="payment"))["requests"]
                    if r["payload"].get("payment_kind") == "invoice" and r["status"] in ("pending", "approved")]
        for r in data["requests"]:
            if r["kind"] != "purchase_order":
                continue
            r["blocking_invoices"] = [
                {**inv, "payment_request_id": next((pr["id"] for pr in payments if pr["ref_id"] == inv["id"]), None)}
                for inv in vendors.get(r["ref_id"], {}).get("open_invoices", [])
            ]
    # payments first: a PO can never be approved before the invoice that blocks it
    order = {"payment": 0, "purchase_order": 1}
    data["requests"].sort(key=lambda r: (order.get(r["kind"], 2), r["id"]))
    return data


def _audit_decision(action: str, approval_id: int, by: str, result: dict, ticket_id: int | None = None) -> None:
    ok = bool(result.get("ok"))
    decision = {"approve": "approved", "reject": "rejected"}[action] if ok else f"{action} refused"
    summary = result.get("error") or result.get("note") or result.get("status", "")
    State.team.audit.append("human_decision", ticket_id=ticket_id, agent="system",
                            reasoning=f"{by} clicked {action}; outcome: {decision}.",
                            detail={"decision": decision, "approval_id": approval_id, "by": by,
                                    "result_summary": summary, "result": result})


def _raise_if_refused(result: dict) -> dict:
    if not result.get("ok"):
        code = 404 if "does not exist" in result.get("error", "") else 409
        raise HTTPException(code, result)
    return result


async def _ticket_of(approval_id: int) -> int | None:
    rows = (await shop("list_approval_requests", status=None))["requests"]
    return next((r["ticket_id"] for r in rows if r["id"] == approval_id), None)


@app.post("/api/approvals/{approval_id}/approve")
async def approve(approval_id: int, body: ApproveBody) -> dict:
    """Human clicked Approve: pays / orders / approves via the human-only MCP tool. Refusals return 409."""
    ticket_id = await _ticket_of(approval_id)
    result = await shop("approve_request", approval_id=approval_id, approved_by=body.approved_by, note=body.note)
    _audit_decision("approve", approval_id, body.approved_by, result, ticket_id)
    _raise_if_refused(result)
    result["ticket_resolved"] = await _auto_resolve(ticket_id, f"All requests decided by {body.approved_by}; ticket closed.")
    return result


@app.post("/api/approvals/{approval_id}/reject")
async def reject(approval_id: int, body: RejectBody) -> dict:
    ticket_id = await _ticket_of(approval_id)
    result = await shop("reject_request", approval_id=approval_id, rejected_by=body.rejected_by, reason=body.reason)
    _audit_decision("reject", approval_id, body.rejected_by, result, ticket_id)
    _raise_if_refused(result)
    result["ticket_resolved"] = await _auto_resolve(ticket_id, f"All requests decided by {body.rejected_by}; ticket closed.")
    return result


# --------------------------------------------------------------------------- #
# Cash and reset
# --------------------------------------------------------------------------- #
@app.get("/api/cash")
async def cash() -> dict:
    """Current checking balance (cash_accounts), plus pending cash-out requests."""
    data = await shop("get_cash_balance")
    checking = next((a for a in data["accounts"] if a["name"] == "checking"), None)
    if checking is None:
        raise HTTPException(404, "No 'checking' account in cash_accounts.")
    return {
        "account": "checking",
        "balance": checking["balance"],
        "as_of": checking["date"],
        "desk_date_today": data["desk_date_today"],
        "pending_cash_requests_total": data["pending_cash_requests_total"],
        "balance_after_all_pending": data["balance_after_all_pending"],
    }


@app.post("/api/reset")
async def reset(body: ResetBody) -> dict:
    """Restore campus_customs_new.db from the original (requires confirm=true; refused during a run)."""
    if not body.confirm:
        raise HTTPException(400, "Set confirm=true to reset the working database.")
    if State.running():
        raise HTTPException(409, "An agent run is in progress; wait for it to finish before resetting.")
    return {"ok": True, **reset_working_db(State.team.audit)}


@app.get("/api/health")
async def health() -> dict:
    try:
        build_model()
        model_ready = True
    except AgentNotConfiguredError:
        model_ready = False
    return {"ok": True, "model_ready": model_ready, "running": [j.run_id for j in State.running()]}
