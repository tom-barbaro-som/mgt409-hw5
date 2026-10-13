"""Brief per-agent summary of one ticket run, built from the audit trail.

Deterministic and free: it reads what the agents already recorded instead of
asking the model to summarize again (no extra tokens).
"""

from __future__ import annotations

import re
from typing import Any

AGENT_ORDER = ["boss", "inventory", "accounting", "facilities", "customer_service"]
TOOL_LABELS = {
    "check_inventory": "checked stock",
    "get_invoice_status": "checked invoice",
    "get_lease_details": "checked lease",
    "list_tickets": "read ticket queue",
    "get_ticket": "read ticket",
    "get_cash_balance": "checked cash",
    "list_vendors": "checked vendors",
    "list_invoices": "listed invoices",
    "get_pricing": "checked pricing",
    "list_approval_requests": "checked approvals",
    "list_payments": "checked payments",
}


def brief(text: str | None, limit: int = 220) -> str:
    """First sentence or two, markdown headings removed, capped in length."""
    if not text:
        return ""
    text = re.sub(r"\*\*[^*]+\*\*", " ", text)
    text = " ".join(text.split())
    sentences = re.split(r"(?<=[.!?])\s+", text)
    out = sentences[0]
    if len(sentences) > 1 and len(out) + len(sentences[1]) < limit:
        out += " " + sentences[1]
    return out if len(out) <= limit else out[: limit - 1].rstrip() + "…"


def _money(value: Any) -> str:
    return f"${value:,.2f}" if isinstance(value, (int, float)) else "?"


def describe_write(tool: str, args: dict, result: Any) -> str | None:
    """One line for an action that changed something (or was refused)."""
    res = result if isinstance(result, dict) else {}
    if res.get("ok") is False:
        return f"Refused {tool.replace('_', ' ')}: {brief(res.get('error'), 140)}"
    rid = res.get("approval_request_id")
    if tool == "request_payment":
        return f"Requested payment #{rid}: {_money(res.get('amount'))} to {res.get('payee')} ({args.get('payment_kind')})"
    if tool == "draft_purchase_order":
        po = res.get("purchase_order", {})
        return f"Drafted PO #{rid}: {po.get('qty')} × {po.get('sku')} {po.get('size')} from {po.get('vendor_name')} ({_money(res.get('amount'))})"
    if tool == "request_price_override":
        po = res.get("price_override", {})
        return f"Requested price override #{rid}: {_money(po.get('unit_price'))}/unit ({po.get('discount_pct')}% off)"
    if tool == "draft_message":
        return f"Drafted message #{rid} to {args.get('recipient')} (not sent)"
    if tool == "set_ticket_status":
        return f"Set ticket status → {res.get('new_status')}"
    if tool == "add_ticket_note":
        return "Added a ticket note"
    return None


def summarize_run(entries: list[dict]) -> dict[str, Any]:
    run_id = entries[0].get("run_id")
    ticket_id = next((e.get("ticket_id") for e in entries if e.get("ticket_id") is not None), None)
    agents: dict[str, dict[str, Any]] = {}
    calls: dict[tuple, dict] = {}
    run: dict[str, Any] = {"run_id": run_id, "ticket_id": ticket_id, "status": "running"}

    def agent(name: str) -> dict[str, Any]:
        return agents.setdefault(name, {
            "agent": name, "delegated_by": [], "delegated_to": [], "checks": [],
            "actions": [], "outcome": "", "tool_calls": 0,
        })

    for e in entries:
        ev, who, d = e["event"], e.get("agent"), e.get("detail", {})
        if ev == "ticket_run_started":
            run["started_at"] = e["ts"]
        elif ev == "delegation":
            agent(who)["delegated_to"].append(d.get("to_agent"))
            if who not in agent(d.get("to_agent"))["delegated_by"]:
                agent(d.get("to_agent"))["delegated_by"].append(who)
        elif ev == "tool_call":
            agent(who)["tool_calls"] += 1
            calls[(who, e.get("step"), d.get("tool"))] = d.get("args", {})
        elif ev == "tool_result":
            tool = d.get("tool")
            args = calls.get((who, e.get("step"), tool), {})
            line = describe_write(tool, args, d.get("result"))
            if line:
                agent(who)["actions"].append(line)
            elif tool in TOOL_LABELS and TOOL_LABELS[tool] not in agent(who)["checks"]:
                agent(who)["checks"].append(TOOL_LABELS[tool])
        elif ev == "agent_finished":
            out = d.get("output", {})
            agent(who)["outcome"] = brief(out.get("decision") or out.get("recommendation") or e.get("reasoning"))
            if who == "boss":
                run["final_status"] = out.get("final_status")
                run["decision"] = brief(out.get("decision"), 300)
                run["next_steps_for_human"] = out.get("next_steps_for_human", [])[:4]
        elif ev == "ticket_run_finished":
            run.update(status=d.get("outcome"), finished_at=e["ts"], usage=d.get("usage", {}),
                       delegations=d.get("delegations"))
        elif ev == "budget_exceeded":
            run["status"] = "paused_for_budget_approval"

    ordered = sorted(agents.values(), key=lambda a: AGENT_ORDER.index(a["agent"]) if a["agent"] in AGENT_ORDER else 99)
    return {**run, "agents": [a for a in ordered if a["agent"] in AGENT_ORDER]}
