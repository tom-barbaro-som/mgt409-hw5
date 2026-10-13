"""Campus Customs MCP server.

Shared toolbox for every agent on the Campus Customs operations team (Boss,
Inventory, Accounting, Facilities, Customer Service). This server is the only
layer that reads or writes shop data, and it works only against the working
copy data/campus_customs_new.db; the original campus_customs.db is never touched.

Tool groups (tags):
  read         - safe lookups, available to every agent
  agent-write  - drafts/requests that agents may create; they never move money
                 and never contact anyone
  human-only   - approve/reject; the ONLY path by which money moves. The backend
                 never exposes these to agents (dashboard/human use only)
  system       - called by the backend itself (e.g. token-budget escalation)

Run (stdio transport):  python mcp_server/server.py
"""

from __future__ import annotations

import calendar
import json
import os
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from fastmcp import FastMCP

HW5_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = HW5_DIR / "data" / "campus_customs_new.db"
# Override with CAMPUS_DB_PATH if needed; defaults to the working copy.
DB_PATH = Path(os.environ.get("CAMPUS_DB_PATH", DEFAULT_DB_PATH)).resolve()

READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}
WRITE = {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False}
MONEY = {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False}

AGENT_NAMES = {"boss", "inventory", "accounting", "facilities", "customer_service"}
REQUESTERS = AGENT_NAMES | {"system"}
TICKET_STATUSES = {"open", "in_progress", "waiting_approval", "blocked", "resolved"}
CASH_OUT_KINDS = ("payment", "purchase_order")
MAX_PO_QTY = 500

mcp = FastMCP(
    name="campus-customs",
    instructions=(
        "Tools for the Campus Customs operations team. Data comes only from the "
        "shop database; 'today' is desk.date_today, not the real-world date. "
        "Agents may draft and request; only a human may approve, and approval is "
        "the only way money moves. Messages are drafts and are never sent. "
        "Never contact customers or vendors."
    ),
)

OPS_SCHEMA = """
CREATE TABLE IF NOT EXISTS approval_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL CHECK (kind IN
        ('payment', 'purchase_order', 'price_override', 'message', 'budget_extension')),
    ticket_id INTEGER,
    ref_id INTEGER,
    amount REAL,
    payload TEXT NOT NULL DEFAULT '{}',
    reason TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    business_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    decided_by TEXT,
    decided_at TEXT,
    decision_note TEXT,
    FOREIGN KEY (ticket_id) REFERENCES tickets(id)
);
"""


# --------------------------------------------------------------------------- #
# Database helpers
# --------------------------------------------------------------------------- #
def _check_db() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Working database not found at {DB_PATH}. "
            "Run scripts/reset_db.py to copy data/campus_customs.db to data/campus_customs_new.db."
        )


def _connect_read_only() -> sqlite3.Connection:
    """Open the working database read-only (never creates or modifies the file)."""
    _check_db()
    conn = sqlite3.connect(f"{DB_PATH.as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _connect_write() -> sqlite3.Connection:
    """Open the working database for writing; callers manage the transaction."""
    _check_db()
    conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(OPS_SCHEMA)
    return conn


def _has_ops_table(conn: sqlite3.Connection) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='approval_requests'"
    ).fetchone() is not None


def _desk_today(conn: sqlite3.Connection) -> date:
    row = conn.execute("SELECT date_today FROM desk LIMIT 1").fetchone()
    return date.fromisoformat(row["date_today"])


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _add_month(d: date) -> date:
    year, month = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def _approval_dict(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["payload"] = json.loads(item.get("payload") or "{}")
    return item


def _open_invoice_ids(conn: sqlite3.Connection, vendor_id: int) -> list[int]:
    rows = conn.execute(
        "SELECT id FROM invoices WHERE vendor_id = ? AND status = 'open' ORDER BY id", (vendor_id,)
    ).fetchall()
    return [r["id"] for r in rows]


def _pending_cash_out(conn: sqlite3.Connection, exclude_id: int | None = None) -> float:
    if not _has_ops_table(conn):
        return 0.0
    row = conn.execute(
        f"SELECT COALESCE(SUM(amount), 0) AS total FROM approval_requests "
        f"WHERE status = 'pending' AND kind IN ({','.join('?' * len(CASH_OUT_KINDS))}) "
        f"AND id != ?",
        (*CASH_OUT_KINDS, exclude_id or -1),
    ).fetchone()
    return round(row["total"], 2)


def _account_balance(conn: sqlite3.Connection, account: str) -> float | None:
    row = conn.execute("SELECT balance FROM cash_accounts WHERE name = ?", (account,)).fetchone()
    return None if row is None else row["balance"]


def _funds_check(conn: sqlite3.Connection, account: str, amount: float, exclude_id: int | None,
                 paying_invoice_of_vendor: int | None = None) -> dict:
    """Can this amount be paid? When paying a vendor's invoice, that vendor's pending POs are
    excluded from the competing total: they cannot be approved until the invoice is paid."""
    balance = _account_balance(conn, account) or 0.0
    pending = _pending_cash_out(conn, exclude_id)
    dependent = 0.0
    if paying_invoice_of_vendor is not None and _has_ops_table(conn):
        dependent = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS t FROM approval_requests WHERE status = 'pending' "
            "AND kind = 'purchase_order' AND ref_id = ?", (paying_invoice_of_vendor,),
        ).fetchone()["t"]
    competing = round(pending - dependent, 2)
    return {
        "account": account,
        "balance": balance,
        "amount": amount,
        "covered_by_balance_now": amount <= balance,
        "other_pending_cash_requests": pending,
        "pending_requests_that_depend_on_this_payment": round(dependent, 2),
        "competing_pending_cash_requests": competing,
        "covered_if_all_other_pending_approved_first": amount <= round(balance - competing, 2),
        "note": ("A request is only refused if the balance is short at the moment a human approves it. "
                 "Always file needed payments; the human chooses the order."),
    }


def _blocking_invoices(conn: sqlite3.Connection, vendor_id: int) -> list[dict]:
    """Open invoices that stop a vendor from shipping, with any payment request already filed."""
    rows = conn.execute(
        "SELECT id, amount, due_date, description FROM invoices WHERE vendor_id = ? AND status = 'open' ORDER BY id",
        (vendor_id,),
    ).fetchall()
    out = []
    for r in rows:
        req = None
        if _has_ops_table(conn):
            req = conn.execute(
                "SELECT id, status FROM approval_requests WHERE kind = 'payment' AND ref_id = ? "
                "AND json_extract(payload, '$.payment_kind') = 'invoice' AND status IN ('pending', 'approved') "
                "ORDER BY id DESC LIMIT 1", (r["id"],),
            ).fetchone()
        out.append({
            **dict(r),
            "payment_request_id": req["id"] if req else None,
            "payment_request_status": req["status"] if req else None,
            "action_needed": None if req else
                f"Accounting must file request_payment(payment_kind='invoice', ref_id={r['id']}) for human approval.",
        })
    return out


def _validate_requester(name: str) -> str | None:
    name = (name or "").strip().lower()
    return name if name in REQUESTERS else None


def _validate_human(name: str) -> str | None:
    """A human approver must be a real name, never an agent or system identity."""
    name = (name or "").strip()
    if not name or name.lower() in REQUESTERS or name.lower() in {"agent", "ai", "bot", "assistant"}:
        return None
    return name


def _insert_approval(conn: sqlite3.Connection, **fields: Any) -> int:
    fields["payload"] = json.dumps(fields.get("payload") or {})
    fields["business_date"] = _desk_today(conn).isoformat()
    fields["created_at"] = _now_utc()
    cols = ", ".join(fields)
    marks = ", ".join("?" * len(fields))
    cur = conn.execute(f"INSERT INTO approval_requests ({cols}) VALUES ({marks})", tuple(fields.values()))
    return cur.lastrowid


def _refuse(error: str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "error": error, **extra}


# --------------------------------------------------------------------------- #
# Read tools (every agent)
# --------------------------------------------------------------------------- #
@mcp.tool(annotations=READ_ONLY, tags={"read"})
def check_inventory(sku: str, size: str | None = None) -> dict[str, Any]:
    """Look up stock on hand for a SKU, optionally for one size.

    Reads the inventory table. Use it to see whether a ticket's requested
    sku/size/qty can be filled from stock (e.g. ticket 101's tee in size S,
    ticket 103's 20 hoodies in size M).

    Args:
        sku: Product code, e.g. "CC-TEE-WHITE".
        size: Optional size, e.g. "S", "M", or "OS" for one-size items.
    """
    sku = sku.strip().upper()
    with _connect_read_only() as conn:
        query = "SELECT sku, name, size, qty, location FROM inventory WHERE sku = ?"
        params: list[Any] = [sku]
        if size:
            query += " AND size = ?"
            params.append(size.strip().upper())
        rows = [dict(r) for r in conn.execute(query, params).fetchall()]

    if not rows:
        target = f"{sku} size {size}" if size else sku
        return {"found": False, "error": f"No inventory row for {target}."}
    return {
        "found": True,
        "sku": sku,
        "name": rows[0]["name"],
        "rows": rows,
        "total_qty": sum(r["qty"] for r in rows),
    }


@mcp.tool(annotations=READ_ONLY, tags={"read"})
def get_invoice_status(invoice_id: int) -> dict[str, Any]:
    """Get an invoice, its vendor, and whether it is overdue as of desk.date_today.

    Reads the invoices, vendors, and desk tables. An open invoice means the
    vendor will not ship new product, so this also reports whether the vendor
    is blocked and the vendor's lead time (e.g. invoice 501 for ticket 101).

    Args:
        invoice_id: Invoice id, e.g. 501.
    """
    with _connect_read_only() as conn:
        inv = conn.execute(
            """
            SELECT i.id, i.vendor_id, i.amount, i.due_date, i.status, i.description,
                   v.name AS vendor_name, v.specialty AS vendor_specialty,
                   v.lead_days AS vendor_lead_days
            FROM invoices i JOIN vendors v ON v.id = i.vendor_id
            WHERE i.id = ?
            """,
            (invoice_id,),
        ).fetchone()
        if inv is None:
            return {"found": False, "error": f"Invoice {invoice_id} does not exist."}
        today = _desk_today(conn)
        open_ids = _open_invoice_ids(conn, inv["vendor_id"])

    invoice = dict(inv)
    days_past_due = (today - date.fromisoformat(invoice["due_date"])).days
    is_open = invoice["status"] == "open"
    return {
        "found": True,
        "invoice": invoice,
        "desk_date_today": today.isoformat(),
        "is_overdue": is_open and days_past_due > 0,
        "days_past_due": max(days_past_due, 0) if is_open else 0,
        "vendor_open_invoice_ids": open_ids,
        "vendor_blocked": bool(open_ids),
    }


@mcp.tool(annotations=READ_ONLY, tags={"read"})
def get_lease_details(lease_id: int) -> dict[str, Any]:
    """Get a lease's rent amount, landlord, and days until rent is due.

    Reads the leases and desk tables. Days until due are counted from
    desk.date_today (e.g. lease 1 for ticket 102's rent notice).

    Args:
        lease_id: Lease id, e.g. 1.
    """
    with _connect_read_only() as conn:
        row = conn.execute(
            "SELECT id, space_name, landlord, monthly_rent, next_due, notes "
            "FROM leases WHERE id = ?",
            (lease_id,),
        ).fetchone()
        if row is None:
            return {"found": False, "error": f"Lease {lease_id} does not exist."}
        today = _desk_today(conn)

    lease = dict(row)
    days_until_due = (date.fromisoformat(lease["next_due"]) - today).days
    return {
        "found": True,
        "lease": lease,
        "desk_date_today": today.isoformat(),
        "days_until_due": days_until_due,
        "is_past_due": days_until_due < 0,
    }


@mcp.tool(annotations=READ_ONLY, tags={"read"})
def list_tickets(status: str | None = "open") -> dict[str, Any]:
    """List tickets, filtered by status ("open" by default; pass null for all).

    Reads the tickets table. The Boss uses this to see the work queue.

    Args:
        status: open, in_progress, waiting_approval, blocked, resolved, or null for all.
    """
    with _connect_read_only() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM tickets WHERE status = ? ORDER BY created_at, id", (status,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM tickets ORDER BY created_at, id").fetchall()
        today = _desk_today(conn)
    return {"desk_date_today": today.isoformat(), "count": len(rows), "tickets": [dict(r) for r in rows]}


@mcp.tool(annotations=READ_ONLY, tags={"read"})
def get_ticket(ticket_id: int) -> dict[str, Any]:
    """Get one ticket with its linked lease, invoice, product rows, and approval requests.

    Reads tickets plus the linked leases, invoices, vendors, inventory, pricing,
    and approval_requests rows, so an agent sees everything the ticket points at.

    Args:
        ticket_id: Ticket id, e.g. 101.
    """
    with _connect_read_only() as conn:
        row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if row is None:
            return {"found": False, "error": f"Ticket {ticket_id} does not exist."}
        ticket = dict(row)
        linked: dict[str, Any] = {}
        if ticket["lease_id"] is not None:
            lease = conn.execute("SELECT * FROM leases WHERE id = ?", (ticket["lease_id"],)).fetchone()
            linked["lease"] = dict(lease) if lease else None
        if ticket["invoice_id"] is not None:
            inv = conn.execute(
                "SELECT i.*, v.name AS vendor_name, v.lead_days AS vendor_lead_days "
                "FROM invoices i JOIN vendors v ON v.id = i.vendor_id WHERE i.id = ?",
                (ticket["invoice_id"],),
            ).fetchone()
            linked["invoice"] = dict(inv) if inv else None
        if ticket["sku"]:
            linked["inventory"] = [
                dict(r) for r in conn.execute(
                    "SELECT sku, name, size, qty, location FROM inventory WHERE sku = ?", (ticket["sku"],)
                ).fetchall()
            ]
            price = conn.execute("SELECT * FROM pricing WHERE sku = ?", (ticket["sku"],)).fetchone()
            linked["pricing"] = dict(price) if price else None
        approvals = []
        if _has_ops_table(conn):
            approvals = [
                _approval_dict(r) for r in conn.execute(
                    "SELECT * FROM approval_requests WHERE ticket_id = ? ORDER BY id", (ticket_id,)
                ).fetchall()
            ]
        today = _desk_today(conn)
    return {
        "found": True,
        "desk_date_today": today.isoformat(),
        "ticket": ticket,
        "linked": linked,
        "approval_requests": approvals,
    }


@mcp.tool(annotations=READ_ONLY, tags={"read"})
def get_cash_balance() -> dict[str, Any]:
    """Get cash account balances and how much cash is already requested but not yet approved.

    Reads cash_accounts, desk, and pending payment/purchase-order approval
    requests. Balances can never go negative, so compare any new spend against
    balance_after_all_pending before recommending it.
    """
    with _connect_read_only() as conn:
        accounts = [dict(r) for r in conn.execute("SELECT * FROM cash_accounts ORDER BY name").fetchall()]
        pending = _pending_cash_out(conn)
        today = _desk_today(conn)
        items = []
        if _has_ops_table(conn):
            for r in conn.execute(
                "SELECT id, kind, ticket_id, ref_id, amount FROM approval_requests "
                "WHERE status = 'pending' AND kind IN ('payment', 'purchase_order') ORDER BY id"
            ).fetchall():
                item = dict(r)
                if r["kind"] == "purchase_order":
                    item["blocked_until_invoices_paid"] = _open_invoice_ids(conn, r["ref_id"])
                items.append(item)
    total = round(sum(a["balance"] for a in accounts), 2)
    return {
        "desk_date_today": today.isoformat(),
        "accounts": accounts,
        "total_balance": total,
        "pending_cash_requests_total": pending,
        "balance_after_all_pending": round(total - pending, 2),
        "covers_all_pending": pending <= total,
        "pending_cash_requests": items,
    }


@mcp.tool(annotations=READ_ONLY, tags={"read"})
def list_vendors() -> dict[str, Any]:
    """List vendors with specialty, lead time, open invoices, and whether they are blocked.

    Reads vendors, invoices, and desk. A vendor with any open invoice will not
    ship new product. earliest_arrival_if_ordered_today = desk date + lead_days
    (only meaningful once the vendor is unblocked).
    """
    with _connect_read_only() as conn:
        today = _desk_today(conn)
        vendors = []
        for v in conn.execute("SELECT * FROM vendors ORDER BY id").fetchall():
            item = dict(v)
            open_rows = conn.execute(
                "SELECT id, amount, due_date FROM invoices WHERE vendor_id = ? AND status = 'open'",
                (v["id"],),
            ).fetchall()
            item["open_invoices"] = [dict(r) for r in open_rows]
            item["amount_owed"] = round(sum(r["amount"] for r in open_rows), 2)
            item["blocked"] = bool(open_rows)
            item["earliest_arrival_if_ordered_today"] = (today + timedelta(days=v["lead_days"])).isoformat()
            vendors.append(item)
    return {"desk_date_today": today.isoformat(), "vendors": vendors}


@mcp.tool(annotations=READ_ONLY, tags={"read"})
def list_invoices(status: str | None = None) -> dict[str, Any]:
    """List invoices (optionally by status, e.g. "open") with overdue status as of desk.date_today.

    Reads invoices, vendors, and desk.

    Args:
        status: Optional filter such as "open" or "paid".
    """
    with _connect_read_only() as conn:
        today = _desk_today(conn)
        query = (
            "SELECT i.*, v.name AS vendor_name FROM invoices i "
            "JOIN vendors v ON v.id = i.vendor_id"
        )
        params: tuple = ()
        if status:
            query += " WHERE i.status = ?"
            params = (status,)
        rows = conn.execute(query + " ORDER BY i.due_date, i.id", params).fetchall()
    invoices = []
    for r in rows:
        item = dict(r)
        days = (today - date.fromisoformat(item["due_date"])).days
        item["is_overdue"] = item["status"] == "open" and days > 0
        item["days_past_due"] = max(days, 0) if item["status"] == "open" else 0
        invoices.append(item)
    return {"desk_date_today": today.isoformat(), "count": len(invoices), "invoices": invoices}


@mcp.tool(annotations=READ_ONLY, tags={"read"})
def get_pricing(sku: str, qty: int = 1, unit_price: float | None = None) -> dict[str, Any]:
    """Get unit cost, list price, and margin for a SKU, optionally at a proposed unit price.

    Reads pricing. Use it before any discount: a price below unit_cost is never allowed.

    Args:
        sku: Product code, e.g. "CC-HOOD-NAVY".
        qty: Units in the order (for totals).
        unit_price: Optional proposed price per unit to evaluate.
    """
    sku = sku.strip().upper()
    with _connect_read_only() as conn:
        row = conn.execute("SELECT * FROM pricing WHERE sku = ?", (sku,)).fetchone()
    if row is None:
        return {"found": False, "error": f"No pricing for {sku}."}
    cost, list_price = row["unit_cost"], row["list_price"]

    def quote(price: float) -> dict[str, Any]:
        return {
            "unit_price": round(price, 2),
            "total_price": round(price * qty, 2),
            "total_cost": round(cost * qty, 2),
            "margin_per_unit": round(price - cost, 2),
            "total_margin": round((price - cost) * qty, 2),
            "margin_pct": round((price - cost) / price * 100, 1) if price else None,
            "discount_pct_vs_list": round((list_price - price) / list_price * 100, 1),
        }

    result: dict[str, Any] = {
        "found": True,
        "sku": sku,
        "qty": qty,
        "unit_cost": cost,
        "list_price": list_price,
        "at_list_price": quote(list_price),
    }
    if unit_price is not None:
        result["at_proposed_price"] = quote(unit_price)
        result["proposed_below_cost"] = unit_price < cost
    return result


@mcp.tool(annotations=READ_ONLY, tags={"read"})
def list_approval_requests(
    status: str | None = "pending", ticket_id: int | None = None, kind: str | None = None
) -> dict[str, Any]:
    """List approval requests (payments, purchase orders, price overrides, message drafts, budgets).

    Reads approval_requests. Check this before creating a request so you do not duplicate one.

    Args:
        status: pending, approved, approved_not_sent, rejected, or null for all.
        ticket_id: Optional ticket filter.
        kind: Optional kind filter (payment, purchase_order, price_override, message, budget_extension).
    """
    with _connect_read_only() as conn:
        if not _has_ops_table(conn):
            return {"count": 0, "requests": []}
        clauses, params = [], []
        for col, val in (("status", status), ("ticket_id", ticket_id), ("kind", kind)):
            if val is not None:
                clauses.append(f"{col} = ?")
                params.append(val)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(f"SELECT * FROM approval_requests{where} ORDER BY id", params).fetchall()
    return {"count": len(rows), "requests": [_approval_dict(r) for r in rows]}


@mcp.tool(annotations=READ_ONLY, tags={"read"})
def list_payments() -> dict[str, Any]:
    """List every recorded payment (the audit ledger of approved cash out).

    Reads payments.
    """
    with _connect_read_only() as conn:
        rows = conn.execute("SELECT * FROM payments ORDER BY id").fetchall()
    payments = [dict(r) for r in rows]
    return {"count": len(payments), "total_paid": round(sum(p["amount"] for p in payments), 2), "payments": payments}


# --------------------------------------------------------------------------- #
# Agent write tools: notes, status, drafts, and requests (no money moves)
# --------------------------------------------------------------------------- #
@mcp.tool(annotations=WRITE, tags={"agent-write"})
def add_ticket_note(ticket_id: int, note: str, agent: str) -> dict[str, Any]:
    """Append a dated note to a ticket's notes (existing notes are never erased).

    Writes tickets.notes.

    Args:
        ticket_id: Ticket id.
        note: Short factual note (findings, actions, or what is waiting on whom).
        agent: Your agent name (filled in automatically by the backend).
    """
    agent_name = _validate_requester(agent)
    if not agent_name:
        return _refuse(f"Unknown agent '{agent}'.")
    if not note.strip():
        return _refuse("Note is empty.")
    conn = _connect_write()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT notes FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if row is None:
            conn.execute("ROLLBACK")
            return _refuse(f"Ticket {ticket_id} does not exist.")
        stamp = f"[{_desk_today(conn).isoformat()} {agent_name}] {note.strip()}"
        notes = f"{row['notes']}\n{stamp}" if row["notes"] else stamp
        conn.execute("UPDATE tickets SET notes = ? WHERE id = ?", (notes, ticket_id))
        conn.execute("COMMIT")
    finally:
        conn.close()
    return {"ok": True, "ticket_id": ticket_id, "appended": stamp}


@mcp.tool(annotations=WRITE, tags={"agent-write"})
def set_ticket_status(ticket_id: int, status: str, reason: str, agent: str = "boss") -> dict[str, Any]:
    """Change a ticket's status and append the reason to its notes. Boss only (plus the backend).

    Writes tickets.status and tickets.notes. A ticket may only be marked
    "resolved" when nothing it depends on is still pending human approval.

    Args:
        ticket_id: Ticket id.
        status: open, in_progress, waiting_approval, blocked, or resolved.
        reason: Why the status is changing.
        agent: Your agent name (filled in automatically by the backend).
    """
    agent_name = _validate_requester(agent)
    if agent_name not in ("boss", "system"):
        return _refuse("Only the Boss (or the backend after a human decision) may change ticket status.")
    status = status.strip().lower()
    if status not in TICKET_STATUSES:
        return _refuse(f"Status must be one of {sorted(TICKET_STATUSES)}.")
    conn = _connect_write()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT status, notes FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if row is None:
            conn.execute("ROLLBACK")
            return _refuse(f"Ticket {ticket_id} does not exist.")
        if status == "resolved":
            pending = conn.execute(
                "SELECT id FROM approval_requests WHERE ticket_id = ? AND status = 'pending'", (ticket_id,)
            ).fetchall()
            if pending:
                conn.execute("ROLLBACK")
                return _refuse(
                    "Ticket still has pending approval requests; use waiting_approval instead.",
                    pending_approval_ids=[r["id"] for r in pending],
                )
        stamp = f"[{_desk_today(conn).isoformat()} {agent_name}] status {row['status']} -> {status}: {reason.strip()}"
        notes = f"{row['notes']}\n{stamp}" if row["notes"] else stamp
        conn.execute("UPDATE tickets SET status = ?, notes = ? WHERE id = ?", (status, notes, ticket_id))
        conn.execute("COMMIT")
    finally:
        conn.close()
    return {"ok": True, "ticket_id": ticket_id, "old_status": row["status"], "new_status": status}


@mcp.tool(annotations=WRITE, tags={"agent-write"})
def request_payment(
    payment_kind: Literal["invoice", "rent"],
    ref_id: int,
    reason: str,
    ticket_id: int | None = None,
    account: str = "checking",
    requested_by: str = "accounting",
) -> dict[str, Any]:
    """Draft a payment for human approval. NO money moves until a human approves it.

    Reads invoices/leases/cash_accounts; writes one pending approval_requests row.
    The amount always comes from the database (invoice amount or monthly rent).
    Refuses duplicates and invoices that are not open.

    Args:
        payment_kind: "invoice" (ref_id = invoices.id) or "rent" (ref_id = leases.id).
        ref_id: The invoice or lease id.
        reason: Why this should be paid now (due date, what it unblocks).
        ticket_id: Ticket this payment resolves, if any.
        account: Cash account to pay from (default "checking").
        requested_by: Your agent name (filled in automatically by the backend).
    """
    requester = _validate_requester(requested_by)
    if not requester:
        return _refuse(f"Unknown requester '{requested_by}'.")
    conn = _connect_write()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if _account_balance(conn, account) is None:
            conn.execute("ROLLBACK")
            return _refuse(f"Cash account '{account}' does not exist.")
        if payment_kind == "invoice":
            inv = conn.execute(
                "SELECT i.*, v.name AS vendor_name FROM invoices i JOIN vendors v ON v.id = i.vendor_id "
                "WHERE i.id = ?", (ref_id,),
            ).fetchone()
            if inv is None:
                conn.execute("ROLLBACK")
                return _refuse(f"Invoice {ref_id} does not exist.")
            if inv["status"] != "open":
                conn.execute("ROLLBACK")
                return _refuse(f"Invoice {ref_id} is '{inv['status']}', not open; nothing to pay.")
            amount = inv["amount"]
            payload = {"payment_kind": "invoice", "account": account, "payee": inv["vendor_name"],
                       "vendor_id": inv["vendor_id"], "due_date": inv["due_date"],
                       "description": inv["description"]}
        elif payment_kind == "rent":
            lease = conn.execute("SELECT * FROM leases WHERE id = ?", (ref_id,)).fetchone()
            if lease is None:
                conn.execute("ROLLBACK")
                return _refuse(f"Lease {ref_id} does not exist.")
            amount = lease["monthly_rent"]
            payload = {"payment_kind": "rent", "account": account, "payee": lease["landlord"],
                       "space_name": lease["space_name"], "due_date": lease["next_due"]}
        else:
            conn.execute("ROLLBACK")
            return _refuse("payment_kind must be 'invoice' or 'rent'.")

        dup = conn.execute(
            "SELECT id, status FROM approval_requests WHERE kind = 'payment' AND ref_id = ? "
            "AND json_extract(payload, '$.payment_kind') = ? AND json_extract(payload, '$.due_date') = ? "
            "AND status IN ('pending', 'approved')",
            (ref_id, payment_kind, payload["due_date"]),
        ).fetchone()
        if dup:
            conn.execute("ROLLBACK")
            return _refuse(f"A payment request already exists for this {payment_kind} (request {dup['id']}, "
                           f"{dup['status']}).", existing_request_id=dup["id"])
        funds = _funds_check(conn, account, amount, None,
                             paying_invoice_of_vendor=payload.get("vendor_id") if payment_kind == "invoice" else None)
        approval_id = _insert_approval(
            conn, kind="payment", ticket_id=ticket_id, ref_id=ref_id, amount=amount,
            payload=payload, reason=reason.strip(), requested_by=requester,
        )
        conn.execute("COMMIT")
    finally:
        conn.close()
    return {
        "ok": True,
        "approval_request_id": approval_id,
        "status": "pending",
        "amount": amount,
        "payee": payload["payee"],
        "funds_check": funds,
        "note": "Drafted only. No money has moved; a human must approve this request.",
    }


@mcp.tool(annotations=WRITE, tags={"agent-write"})
def draft_purchase_order(
    vendor_id: int,
    sku: str,
    size: str,
    qty: int,
    reason: str,
    ticket_id: int | None = None,
    requested_by: str = "inventory",
) -> dict[str, Any]:
    """Draft a restock purchase order for human approval. NO money moves and nothing is sent.

    Reads vendors, invoices, inventory, pricing; writes one pending approval_requests row.
    Cost = qty x pricing.unit_cost. If the vendor has an open invoice, the PO is
    still drafted but flagged: it cannot be approved until that invoice is paid.

    Args:
        vendor_id: Vendor to order from (match the vendor specialty to the product).
        sku: Product code.
        size: Size to restock (must be an existing inventory size for the SKU).
        qty: Units to order (1-500).
        reason: Why the restock is needed (shortage, ticket).
        ticket_id: Ticket this restock supports, if any.
        requested_by: Your agent name (filled in automatically by the backend).
    """
    requester = _validate_requester(requested_by)
    if not requester:
        return _refuse(f"Unknown requester '{requested_by}'.")
    if not 1 <= qty <= MAX_PO_QTY:
        return _refuse(f"qty must be between 1 and {MAX_PO_QTY}.")
    sku, size = sku.strip().upper(), size.strip().upper()
    conn = _connect_write()
    try:
        conn.execute("BEGIN IMMEDIATE")
        vendor = conn.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id,)).fetchone()
        item = conn.execute("SELECT * FROM inventory WHERE sku = ? AND size = ?", (sku, size)).fetchone()
        price = conn.execute("SELECT * FROM pricing WHERE sku = ?", (sku,)).fetchone()
        if vendor is None or item is None or price is None:
            conn.execute("ROLLBACK")
            missing = "vendor" if vendor is None else "inventory row" if item is None else "pricing"
            return _refuse(f"Cannot draft PO: {missing} not found for vendor {vendor_id}, {sku} {size}.")
        dup = conn.execute(
            "SELECT id FROM approval_requests WHERE kind = 'purchase_order' AND status = 'pending' "
            "AND json_extract(payload, '$.sku') = ? AND json_extract(payload, '$.size') = ? "
            "AND ticket_id IS ?",
            (sku, size, ticket_id),
        ).fetchone()
        if dup:
            conn.execute("ROLLBACK")
            return _refuse(f"A pending PO already exists for {sku} {size} (request {dup['id']}).",
                           existing_request_id=dup["id"])
        today = _desk_today(conn)
        open_ids = _open_invoice_ids(conn, vendor_id)
        amount = round(qty * price["unit_cost"], 2)
        payload = {
            "vendor_id": vendor_id, "vendor_name": vendor["name"], "vendor_specialty": vendor["specialty"],
            "sku": sku, "size": size, "product_name": item["name"], "qty": qty,
            "unit_cost": price["unit_cost"], "lead_days": vendor["lead_days"], "account": "checking",
            "expected_arrival_if_approved_today": (today + timedelta(days=vendor["lead_days"])).isoformat(),
            "vendor_blocked_by_invoices": open_ids,
        }
        funds = _funds_check(conn, "checking", amount, None)
        approval_id = _insert_approval(
            conn, kind="purchase_order", ticket_id=ticket_id, ref_id=vendor_id, amount=amount,
            payload=payload, reason=reason.strip(), requested_by=requester,
        )
        conn.execute("COMMIT")
    finally:
        conn.close()
    result = {
        "ok": True,
        "approval_request_id": approval_id,
        "status": "pending",
        "amount": amount,
        "purchase_order": payload,
        "funds_check": funds,
        "note": "Drafted only. Nothing was sent to the vendor and no money has moved.",
    }
    if open_ids:
        with _connect_read_only() as conn:
            must_pay = _blocking_invoices(conn, vendor_id)
        result["must_pay_first"] = must_pay
        result["warning"] = (f"{vendor['name']} has open invoice(s) {open_ids}; this PO cannot be approved until "
                             "they are paid. File a payment request for each one that has none "
                             "(payment_request_id is null) so the human can approve it first.")
    return result


@mcp.tool(annotations=WRITE, tags={"agent-write"})
def request_price_override(
    sku: str,
    qty: int,
    unit_price: float,
    reason: str,
    ticket_id: int | None = None,
    size: str | None = None,
    requested_by: str = "accounting",
) -> dict[str, Any]:
    """Request a human-approved discounted unit price. Refuses any price below unit cost.

    Reads pricing and inventory; writes one pending approval_requests row. No
    cash moves (revenue is not modeled).

    Args:
        sku: Product code.
        qty: Units the discount applies to.
        unit_price: Proposed price per unit (must be >= unit_cost and < list_price).
        reason: Business justification (bulk size, customer, margin kept).
        ticket_id: Ticket asking for the discount, if any.
        size: Size, if relevant.
        requested_by: Your agent name (filled in automatically by the backend).
    """
    requester = _validate_requester(requested_by)
    if not requester:
        return _refuse(f"Unknown requester '{requested_by}'.")
    if qty < 1:
        return _refuse("qty must be at least 1.")
    sku = sku.strip().upper()
    size = size.strip().upper() if size else None
    conn = _connect_write()
    try:
        conn.execute("BEGIN IMMEDIATE")
        price = conn.execute("SELECT * FROM pricing WHERE sku = ?", (sku,)).fetchone()
        if price is None:
            conn.execute("ROLLBACK")
            return _refuse(f"No pricing for {sku}.")
        cost, list_price = price["unit_cost"], price["list_price"]
        if unit_price < cost:
            conn.execute("ROLLBACK")
            return _refuse(f"Refused: ${unit_price:.2f} is below unit cost ${cost:.2f}.")
        if unit_price >= list_price:
            conn.execute("ROLLBACK")
            return _refuse(f"${unit_price:.2f} is not a discount (list price ${list_price:.2f}).")
        dup = conn.execute(
            "SELECT id FROM approval_requests WHERE kind = 'price_override' AND status = 'pending' "
            "AND ticket_id IS ? AND json_extract(payload, '$.sku') = ?", (ticket_id, sku),
        ).fetchone()
        if dup:
            conn.execute("ROLLBACK")
            return _refuse(f"A pending price override already exists (request {dup['id']}).",
                           existing_request_id=dup["id"])
        stock = None
        if size:
            row = conn.execute("SELECT qty FROM inventory WHERE sku = ? AND size = ?", (sku, size)).fetchone()
            stock = row["qty"] if row else None
        payload = {
            "sku": sku, "size": size, "qty": qty, "unit_price": round(unit_price, 2),
            "list_price": list_price, "unit_cost": cost,
            "discount_pct": round((list_price - unit_price) / list_price * 100, 1),
            "margin_per_unit": round(unit_price - cost, 2),
            "margin_pct": round((unit_price - cost) / unit_price * 100, 1),
            "total_price": round(unit_price * qty, 2), "total_at_list": round(list_price * qty, 2),
            "units_in_stock_for_size": stock,
        }
        approval_id = _insert_approval(
            conn, kind="price_override", ticket_id=ticket_id, ref_id=None, amount=None,
            payload=payload, reason=reason.strip(), requested_by=requester,
        )
        conn.execute("COMMIT")
    finally:
        conn.close()
    return {"ok": True, "approval_request_id": approval_id, "status": "pending", "price_override": payload,
            "note": "Requested only. The discount is not offered to anyone until a human approves it."}


@mcp.tool(annotations=WRITE, tags={"agent-write"})
def draft_message(
    recipient: str,
    subject: str,
    body: str,
    reason: str,
    ticket_id: int | None = None,
    channel: str = "email",
    drafted_by: str = "customer_service",
) -> dict[str, Any]:
    """Save a DRAFT message for human review. This tool NEVER sends anything.

    Writes one pending approval_requests row (kind "message"). There is no send
    tool: even after approval the draft is marked approved_not_sent.

    Args:
        recipient: Who the draft is addressed to (name from the ticket/vendor/lease).
        subject: Subject line.
        body: Full draft text.
        reason: Why this message is needed.
        ticket_id: Related ticket, if any.
        channel: Intended channel (email, phone script, letter) - informational only.
        drafted_by: Your agent name (filled in automatically by the backend).
    """
    requester = _validate_requester(drafted_by)
    if not requester:
        return _refuse(f"Unknown drafter '{drafted_by}'.")
    if not recipient.strip() or not body.strip():
        return _refuse("Recipient and body are required.")
    conn = _connect_write()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if ticket_id is not None and conn.execute(
            "SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)
        ).fetchone() is None:
            conn.execute("ROLLBACK")
            return _refuse(f"Ticket {ticket_id} does not exist.")
        payload = {"recipient": recipient.strip(), "channel": channel, "subject": subject.strip(),
                   "body": body.strip(), "sent": False}
        approval_id = _insert_approval(
            conn, kind="message", ticket_id=ticket_id, ref_id=None, amount=None,
            payload=payload, reason=reason.strip(), requested_by=requester,
        )
        conn.execute("COMMIT")
    finally:
        conn.close()
    return {"ok": True, "approval_request_id": approval_id, "status": "pending", "sent": False,
            "note": "DRAFT saved. Not sent. No external contact is ever made by this system."}


# --------------------------------------------------------------------------- #
# System tool (backend only): token budget escalation
# --------------------------------------------------------------------------- #
@mcp.tool(annotations=WRITE, tags={"system"})
def request_budget_extension(
    ticket_id: int, tokens_used: int, tokens_requested: int, reason: str, requested_by: str = "system"
) -> dict[str, Any]:
    """Ask a human to approve more AI token budget for a ticket that hit its limit.

    Writes one pending approval_requests row (kind "budget_extension"). Called by
    the backend when a ticket run exceeds its token/request budget.
    """
    requester = _validate_requester(requested_by)
    if not requester:
        return _refuse(f"Unknown requester '{requested_by}'.")
    conn = _connect_write()
    try:
        conn.execute("BEGIN IMMEDIATE")
        approval_id = _insert_approval(
            conn, kind="budget_extension", ticket_id=ticket_id, ref_id=None, amount=None,
            payload={"tokens_used": tokens_used, "tokens_requested": tokens_requested},
            reason=reason.strip(), requested_by=requester,
        )
        conn.execute("COMMIT")
    finally:
        conn.close()
    return {"ok": True, "approval_request_id": approval_id, "status": "pending"}


# --------------------------------------------------------------------------- #
# Human-only tools: the only path by which money moves
# --------------------------------------------------------------------------- #
def _pay(conn: sqlite3.Connection, req: sqlite3.Row, pay_kind: str, ref_id: int, account: str,
         approver: str, today: date) -> dict[str, Any] | None:
    """Deduct cash and record the payment inside the caller's transaction; None if refused."""
    amount = req["amount"]
    cur = conn.execute(
        "UPDATE cash_accounts SET balance = ROUND(balance - ?, 2), date = ? WHERE name = ? AND balance >= ?",
        (amount, today.isoformat(), account, amount),
    )
    if cur.rowcount != 1:
        return None
    pay = conn.execute(
        "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) VALUES (?, ?, ?, ?, ?, ?)",
        (pay_kind, ref_id, amount, account, today.isoformat(), approver),
    )
    new_balance = _account_balance(conn, account)
    return {"payment_id": pay.lastrowid, "amount": amount, "account": account, "new_balance": new_balance}


@mcp.tool(annotations=MONEY, tags={"human-only"})
def approve_request(approval_id: int, approved_by: str, note: str | None = None) -> dict[str, Any]:
    """HUMAN ONLY. Approve a pending request and carry it out.

    - payment: refuses if the account lacks cash (balances never go negative);
      otherwise deducts cash, records a payments row, and marks the invoice
      paid or advances the lease's next_due by one month.
    - purchase_order: refuses if the vendor still has an open invoice or cash is
      short; otherwise pays the PO cost and records the expected arrival date.
      Nothing is sent to the vendor.
    - price_override: marks the discount approved (no cash moves).
    - message: marks the draft approved_not_sent. Nothing is ever sent.
    - budget_extension: grants the extra token budget for the ticket.

    Args:
        approval_id: approval_requests.id
        approved_by: Name of the human approver (agent names are rejected).
        note: Optional note from the approver.
    """
    approver = _validate_human(approved_by)
    if not approver:
        return _refuse("approved_by must be a human's name; agents cannot approve.")
    conn = _connect_write()
    try:
        conn.execute("BEGIN IMMEDIATE")
        req = conn.execute("SELECT * FROM approval_requests WHERE id = ?", (approval_id,)).fetchone()
        if req is None:
            conn.execute("ROLLBACK")
            return _refuse(f"Approval request {approval_id} does not exist.")
        if req["status"] != "pending":
            conn.execute("ROLLBACK")
            return _refuse(f"Request {approval_id} is already '{req['status']}'.")
        payload = json.loads(req["payload"])
        today = _desk_today(conn)
        result: dict[str, Any] = {"ok": True, "approval_request_id": approval_id, "kind": req["kind"]}
        new_status = "approved"

        if req["kind"] == "payment":
            account = payload.get("account", "checking")
            if payload["payment_kind"] == "invoice":
                inv = conn.execute("SELECT status FROM invoices WHERE id = ?", (req["ref_id"],)).fetchone()
                if inv is None or inv["status"] != "open":
                    conn.execute("ROLLBACK")
                    return _refuse(f"Invoice {req['ref_id']} is no longer open.")
            paid = _pay(conn, req, payload["payment_kind"], req["ref_id"], account, approver, today)
            if paid is None:
                conn.execute("ROLLBACK")
                return _refuse(
                    f"Refused: account '{account}' has ${_account_balance(conn, account):.2f}, "
                    f"less than ${req['amount']:.2f}. Balances cannot go negative. Request stays pending.",
                    refused_for="insufficient_funds",
                )
            if payload["payment_kind"] == "invoice":
                conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (req["ref_id"],))
                result["invoice_status"] = "paid"
            else:
                lease = conn.execute("SELECT next_due, notes FROM leases WHERE id = ?", (req["ref_id"],)).fetchone()
                new_due = _add_month(date.fromisoformat(lease["next_due"])).isoformat()
                stamp = f"[{today.isoformat()}] Rent due {lease['next_due']} paid (payment {paid['payment_id']})."
                notes = f"{lease['notes']}\n{stamp}" if lease["notes"] else stamp
                conn.execute("UPDATE leases SET next_due = ?, notes = ? WHERE id = ?", (new_due, notes, req["ref_id"]))
                result["lease_next_due"] = new_due
            result["payment"] = paid

        elif req["kind"] == "purchase_order":
            open_ids = _open_invoice_ids(conn, payload["vendor_id"])
            if open_ids:
                blocking = _blocking_invoices(conn, payload["vendor_id"])
                conn.execute("ROLLBACK")
                pending_ids = [b["payment_request_id"] for b in blocking if b["payment_request_id"]]
                hint = (f" Approve payment request(s) {pending_ids} first." if pending_ids else
                        " No payment request exists for it yet; run the agents on the ticket so Accounting files one.")
                return _refuse(f"Refused: vendor {payload['vendor_name']} has open invoice(s) {open_ids}; "
                               f"they will not ship until paid. Request stays pending.{hint}",
                               refused_for="vendor_blocked", blocking_invoices=blocking)
            paid = _pay(conn, req, "purchase_order", approval_id, payload.get("account", "checking"), approver, today)
            if paid is None:
                conn.execute("ROLLBACK")
                return _refuse(
                    f"Refused: not enough cash for ${req['amount']:.2f}. Balances cannot go negative. "
                    "Request stays pending.", refused_for="insufficient_funds",
                )
            payload["expected_arrival"] = (today + timedelta(days=payload["lead_days"])).isoformat()
            payload["ordered_on"] = today.isoformat()
            result["payment"] = paid
            result["expected_arrival"] = payload["expected_arrival"]
            result["note"] = "Order recorded internally only; nothing was sent to the vendor."

        elif req["kind"] == "message":
            new_status = "approved_not_sent"
            result["note"] = "Draft approved for the record. It has NOT been sent; this system never sends."

        conn.execute(
            "UPDATE approval_requests SET status = ?, payload = ?, decided_by = ?, decided_at = ?, "
            "decision_note = ? WHERE id = ?",
            (new_status, json.dumps(payload), approver, _now_utc(), note, approval_id),
        )
        conn.execute("COMMIT")
    finally:
        conn.close()
    result["status"] = new_status
    return result


@mcp.tool(annotations=WRITE, tags={"human-only"})
def reject_request(approval_id: int, rejected_by: str, reason: str) -> dict[str, Any]:
    """HUMAN ONLY. Reject a pending request. Nothing is paid, ordered, or sent.

    Args:
        approval_id: approval_requests.id
        rejected_by: Name of the human (agent names are rejected).
        reason: Why it was rejected (agents read this on the next run).
    """
    human = _validate_human(rejected_by)
    if not human:
        return _refuse("rejected_by must be a human's name; agents cannot reject.")
    conn = _connect_write()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            "UPDATE approval_requests SET status = 'rejected', decided_by = ?, decided_at = ?, decision_note = ? "
            "WHERE id = ? AND status = 'pending'",
            (human, _now_utc(), reason, approval_id),
        )
        conn.execute("COMMIT")
    finally:
        conn.close()
    if cur.rowcount != 1:
        return _refuse(f"Request {approval_id} does not exist or is not pending.")
    return {"ok": True, "approval_request_id": approval_id, "status": "rejected"}


if __name__ == "__main__":
    mcp.run(show_banner=False)
