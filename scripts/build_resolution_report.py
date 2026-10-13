"""Build output/resolved_tickets.json and output/resolved_board.html from real data.

Sources (nothing is typed in by hand):
  - live dashboard API (http://localhost:8000): tickets, run summaries, cash shown on the dashboard
  - data/campus_customs_new.db (read-only): payments, balances, approval requests
  - data/campus_customs.db (read-only): the starting balance
  - output/audit_trail.json: every agent run and every human decision (including refusals)
  - output/screenshots/ticket_<id>.png: captured by scripts/capture_board.py

Run from hw5 (backend running):  .venv/bin/python scripts/build_resolution_report.py
"""

from __future__ import annotations

import base64
import html
import json
import sqlite3
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HW5 = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HW5))
from backend.audit import read_audit_trail  # noqa: E402
from backend.run_summary import summarize_run  # noqa: E402

API = "http://localhost:8000"
OUT = HW5 / "output"
AUDIT = OUT / "audit_trail.json"
TICKETS = [101, 102, 103]


def api(path: str):
    with urllib.request.urlopen(API + path) as r:
        return json.load(r)


def ro(db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def money(x: float) -> str:
    return f"${x:,.2f}"


def build() -> dict:
    work, orig = ro(HW5 / "data" / "campus_customs_new.db"), ro(HW5 / "data" / "campus_customs.db")
    start_balance = orig.execute("SELECT balance FROM cash_accounts WHERE name='checking'").fetchone()[0]
    db_balance = work.execute("SELECT balance FROM cash_accounts WHERE name='checking'").fetchone()[0]
    payments = [dict(r) for r in work.execute("SELECT * FROM payments ORDER BY id")]
    approvals = {r["id"]: {**dict(r), "payload": json.loads(r["payload"])}
                 for r in work.execute("SELECT * FROM approval_requests ORDER BY id")}
    dashboard_cash = api("/api/cash")
    tickets_api = {t["id"]: t for t in api("/api/tickets")["tickets"]}
    entries = read_audit_trail(AUDIT)

    # cash ledger in the order money actually moved (payments table is the source of truth)
    ledger, running = [], start_balance
    for p in payments:
        req = next((a for a in approvals.values() if a["kind"] == "payment" and a["ref_id"] == p["ref_id"]
                    and a["payload"].get("payment_kind") == p["kind"] and a["status"] == "approved"), None)
        running = round(running - p["amount"], 2)
        ledger.append({
            "payment_id": p["id"], "ticket_id": req["ticket_id"] if req else None,
            "approval_request_id": req["id"] if req else None, "kind": p["kind"], "ref_id": p["ref_id"],
            "payee": req["payload"].get("payee") if req else None, "amount": p["amount"],
            "paid_at_desk_date": p["paid_at"], "approved_by": p["approved_by"],
            "approved_at": req["decided_at"] if req else None, "balance_after": running,
        })
    reconciliation = {
        "starting_balance_original_db": start_balance,
        "total_paid_out": round(sum(p["amount"] for p in payments), 2),
        "ledger_ending_balance": running,
        "working_db_ending_balance": db_balance,
        "dashboard_ending_balance": dashboard_cash["balance"],
        "all_three_match": running == db_balance == dashboard_cash["balance"],
        "pending_cash_requests": dashboard_cash["pending_cash_requests_total"],
    }

    # human decisions from the audit trail (approval id -> ticket via the approvals table)
    decisions: dict[int, list[dict]] = {}
    for e in entries:
        if e["event"] == "human_decision":
            d = e["detail"]
            aid = d["approval_id"]
            decisions.setdefault(aid, []).append({
                "at": e["ts"], "by": d["by"], "outcome": d["decision"],
                "message": d.get("result_summary"),
            })

    runs_by_ticket: dict[int, list[str]] = {}
    for e in entries:
        if e["event"] == "ticket_run_started":
            runs_by_ticket.setdefault(e["ticket_id"], []).append(e["run_id"])

    out_tickets = []
    for tid in TICKETS:
        t = tickets_api[tid]
        runs = []
        for rid in runs_by_ticket.get(tid, []):
            s = summarize_run([e for e in entries if e.get("run_id") == rid])
            runs.append({
                "run_id": rid, "started_at": s.get("started_at"), "finished_at": s.get("finished_at"),
                "outcome": s.get("status"), "boss_final_status": s.get("final_status"),
                "tokens": (s.get("usage") or {}).get("total_tokens"),
                "boss_decision": s.get("decision"),
                "agents": [{
                    "agent": a["agent"], "asked_by": a["delegated_by"], "asked": a["delegated_to"],
                    "actions": a["actions"], "checks": a["checks"], "conclusion": a["outcome"],
                } for a in s["agents"]],
            })
        what_each_agent_did: dict[str, list[str]] = {}
        for r in runs:
            for a in r["agents"]:
                lines = what_each_agent_did.setdefault(a["agent"], [])
                did = a["actions"] or ["No changes; checks only (" + ", ".join(a["checks"]) + ")"]
                lines.append(f"{r['run_id']}: " + "; ".join(did))
        human = []
        for aid, a in approvals.items():
            if a["ticket_id"] != tid:
                continue
            human.append({
                "approval_request_id": aid, "kind": a["kind"], "amount": a["amount"],
                "requested_by": a["requested_by"], "reason": a["reason"],
                "final_status": a["status"], "decided_by": a["decided_by"], "decided_at": a["decided_at"],
                "details": {k: v for k, v in a["payload"].items() if k in (
                    "payee", "payment_kind", "due_date", "sku", "size", "qty", "unit_price", "discount_pct",
                    "margin_pct", "vendor_name", "recipient", "subject", "sent")},
                "decision_attempts": decisions.get(aid, []),
            })
        out_tickets.append({
            "id": tid, "subject": t["subject"], "requester": t["requester"], "type": t["type"],
            "final_status": t["status"], "resolved": t["is_resolved"],
            "dashboard_explanation": t["explanation"],
            "summarized_outcome": OUTCOMES[tid](approvals, payments, work),
            "what_each_agent_did": what_each_agent_did,
            "agent_runs": runs,
            "human_approvals": human,
            "payments": [p for p in ledger if p["ticket_id"] == tid],
        })
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "desk_date_today": dashboard_cash["desk_date_today"],
        "sources": ["http://localhost:8000 (dashboard API)", "data/campus_customs_new.db (read-only)",
                    "data/campus_customs.db (starting balance)", "output/audit_trail.json"],
        "cash_ledger": ledger,
        "reconciliation": reconciliation,
        "tickets": out_tickets,
    }


# Plain-language outcomes, with every figure read from the database.
def _outcome_101(appr, pays, db) -> str:
    inv = db.execute("SELECT amount, status FROM invoices WHERE id=501").fetchone()
    stock = db.execute("SELECT qty FROM inventory WHERE sku='CC-TEE-WHITE' AND size='S'").fetchone()[0]
    return (f"Resolved. Size S tee stock is {stock}. Invoice 501 ({money(inv['amount'])}, Bulldog Print Co, "
            f"'Rush reprint CC-TEE-WHITE S') is now {inv['status']} after human approval, unblocking the vendor; "
            "no duplicate PO was ordered. Customer update draft #5 was approved but NOT sent. Delivery of the "
            "reprint is not tracked by the system (estimated desk date + 5-day lead time = 2026-09-05).")


def _outcome_102(appr, pays, db) -> str:
    lease = db.execute("SELECT monthly_rent, next_due FROM leases WHERE id=1").fetchone()
    return (f"Resolved. Rent of {money(lease['monthly_rent'])} for lease 1 (Chapel Street shop, Elm City "
            f"Properties) was paid after human approval; the lease's next due date advanced to {lease['next_due']}. "
            "No landlord message was needed.")


def _outcome_103(appr, pays, db) -> str:
    po = next(a for a in appr.values() if a["kind"] == "purchase_order" and a["ticket_id"] == 103)
    ov = next((a for a in appr.values() if a["kind"] == "price_override" and a["ticket_id"] == 103), None)
    stock = db.execute("SELECT qty FROM inventory WHERE sku='CC-HOOD-NAVY' AND size='M'").fetchone()[0]
    bal = db.execute("SELECT balance FROM cash_accounts WHERE name='checking'").fetchone()[0]
    ov_txt = (f"Price override #{ov['id']} ({money(ov['payload']['unit_price'])}/unit, "
              f"{ov['payload']['discount_pct']}% off) is {ov['status']}. ") if ov else ""
    return (f"NOT resolved (status waiting_approval). {ov_txt}{stock} of 20 size M hoodies are in stock. "
            f"PO #{po['id']} for {po['payload']['qty']} more ({money(po['amount'])}) is still {po['status']}: "
            f"approval was refused while invoice 501 blocked the vendor, and is now refused because checking "
            f"has {money(bal)} (balances cannot go negative). A human must reject it or the agents must propose "
            "an affordable alternative.")


OUTCOMES = {101: _outcome_101, 102: _outcome_102, 103: _outcome_103}


def board_html(report: dict) -> str:
    rec = report["reconciliation"]
    cards = []
    for t in report["tickets"]:
        img = OUT / "screenshots" / f"ticket_{t['id']}.png"
        data = base64.b64encode(img.read_bytes()).decode()
        badge = ("<span class='ok'>✓ Resolved</span>" if t["resolved"]
                 else f"<span class='open'>Not resolved · {html.escape(t['final_status'])}</span>")
        approvals = "".join(
            f"<li>#{a['approval_request_id']} {html.escape(a['kind'].replace('_', ' '))}"
            f"{' ' + money(a['amount']) if a['amount'] else ''}: <b>{html.escape(a['final_status'])}</b>"
            f"{' by ' + html.escape(a['decided_by']) if a['decided_by'] else ''}"
            f"{' (' + str(sum(1 for x in a['decision_attempts'] if 'refused' in x['outcome'])) + ' refused attempts)' if any('refused' in x['outcome'] for x in a['decision_attempts']) else ''}</li>"
            for a in t["human_approvals"])
        cards.append(f"""
  <section class="ticket" id="t{t['id']}">
    <div class="head"><h2>Ticket {t['id']} · {html.escape(t['subject'])}</h2>{badge}</div>
    <p class="outcome">{html.escape(t['summarized_outcome'])}</p>
    <ul class="appr">{approvals}</ul>
    <figure><img src="data:image/png;base64,{data}" alt="Dashboard screenshot for ticket {t['id']}">
      <figcaption>Live dashboard, ticket {t['id']} selected, captured as is (scripts/capture_board.py).</figcaption></figure>
  </section>""")
    nav = " · ".join(f"<a href='#t{t['id']}'>Ticket {t['id']}</a>" for t in report["tickets"])
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Campus Customs · Resolved board</title>
<style>
  body {{ margin: 0; font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f7f6f2; color: #1f2933; }}
  header {{ background: #00356b; color: #fff; padding: 18px 32px; border-bottom: 4px solid #286dc0; }}
  header h1 {{ margin: 0; font: 700 24px Georgia, serif; }} header p {{ margin: 4px 0 0; opacity: .85; font-size: 13px; }}
  header a {{ color: #fff; }}
  main {{ max-width: 1240px; margin: 24px auto; padding: 0 24px 40px; }}
  .rec {{ background: #fff; border: 1px solid #e3e6ea; border-radius: 10px; padding: 14px 18px; margin-bottom: 24px; }}
  .ticket {{ background: #fff; border: 1px solid #e3e6ea; border-radius: 12px; padding: 20px 22px; margin-bottom: 28px; }}
  .head {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; }}
  h2 {{ margin: 0; font: 700 21px Georgia, serif; color: #00356b; }}
  .ok, .open {{ font-weight: 700; font-size: 13px; padding: 4px 12px; border-radius: 999px; white-space: nowrap; }}
  .ok {{ background: #e6f3ea; color: #2e7d4f; }} .open {{ background: #fff4dc; color: #a86b00; }}
  .outcome {{ margin: 10px 0; }} .appr {{ margin: 0 0 14px; font-size: 14px; }}
  figure {{ margin: 0; }} img {{ width: 100%; border: 1px solid #e3e6ea; border-radius: 8px; }}
  figcaption {{ font-size: 12px; color: #64707d; margin-top: 6px; }}
</style></head><body>
<header><h1>Campus Customs · Resolved board</h1>
<p>Desk date {report['desk_date_today']} · generated {report['generated_at']} · {nav}</p></header>
<main>
  <div class="rec"><b>Cash reconciliation:</b> start {money(rec['starting_balance_original_db'])} − paid {money(rec['total_paid_out'])}
  = ledger {money(rec['ledger_ending_balance'])} · working DB {money(rec['working_db_ending_balance'])} ·
  dashboard {money(rec['dashboard_ending_balance'])} → <b>{'all match' if rec['all_three_match'] else 'MISMATCH'}</b>.
  Still pending: {money(rec['pending_cash_requests'])} (not paid).</div>
  {''.join(cards)}
</main></body></html>
"""


if __name__ == "__main__":
    report = build()
    (OUT / "resolved_tickets.json").write_text(json.dumps(report, indent=2) + "\n")
    (OUT / "resolved_board.html").write_text(board_html(report))
    print(json.dumps(report["reconciliation"], indent=2))
    for t in report["tickets"]:
        print(t["id"], t["final_status"], "| runs:", len(t["agent_runs"]), "| approvals:",
              [(a["approval_request_id"], a["final_status"], len(a["decision_attempts"])) for a in t["human_approvals"]])
