"""Smoke-test the Campus Customs MCP server through the .mcp.json connection.

Launches the server exactly as configured in hw5/.mcp.json (stdio transport),
calls each tool, checks every result against a direct read-only SQL query on
data/campus_customs_new.db, and writes output/mcp_smoke.json.

Run from hw5:  .venv/bin/python scripts/mcp_smoke.py
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastmcp import Client

HW5_DIR = Path(__file__).resolve().parent.parent
MCP_JSON = HW5_DIR / ".mcp.json"
DB_PATH = HW5_DIR / "data" / "campus_customs_new.db"
OUT_PATH = HW5_DIR / "output" / "mcp_smoke_rerun.json"


def sha1(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def db_rows(sql: str, params: tuple = ()) -> list[dict]:
    conn = sqlite3.connect(f"{DB_PATH.as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


TESTS = [
    {
        "ticket": 101,
        "prompt": "Ticket 101: Tauhid Zaman wants 1 Classic Bulldog Tee (CC-TEE-WHITE) in size S. "
        "How many are in stock?",
        "tool": "check_inventory",
        "args": {"sku": "CC-TEE-WHITE", "size": "S"},
        "db_query": "SELECT sku, name, size, qty, location FROM inventory WHERE sku = ? AND size = ?",
        "db_params": ("CC-TEE-WHITE", "S"),
        "compare": lambda out, db: out["rows"] == db,
    },
    {
        "ticket": 103,
        "prompt": "Ticket 103: Yale AI Club wants 20 Basic Hoodie Big Yale (CC-HOOD-NAVY) in size M. "
        "How many are in stock?",
        "tool": "check_inventory",
        "args": {"sku": "CC-HOOD-NAVY", "size": "M"},
        "db_query": "SELECT sku, name, size, qty, location FROM inventory WHERE sku = ? AND size = ?",
        "db_params": ("CC-HOOD-NAVY", "M"),
        "compare": lambda out, db: out["rows"] == db,
    },
    {
        "ticket": 101,
        "prompt": "Ticket 101 links to invoice 501. Is it paid, is it overdue as of the shop's "
        "desk date, and is the vendor blocked from shipping?",
        "tool": "get_invoice_status",
        "args": {"invoice_id": 501},
        "db_query": "SELECT i.id, i.vendor_id, i.amount, i.due_date, i.status, i.description, "
        "v.name AS vendor_name, v.specialty AS vendor_specialty, v.lead_days AS vendor_lead_days, "
        "(SELECT date_today FROM desk) AS desk_date_today "
        "FROM invoices i JOIN vendors v ON v.id = i.vendor_id WHERE i.id = ?",
        "db_params": (501,),
        "compare": lambda out, db: (
            {k: v for k, v in db[0].items() if k != "desk_date_today"} == out["invoice"]
            and db[0]["desk_date_today"] == out["desk_date_today"]
        ),
    },
    {
        "ticket": 102,
        "prompt": "Ticket 102: Elm City Properties sent a rent notice for lease 1. How much rent "
        "is owed and how many days until it is due from the shop's desk date?",
        "tool": "get_lease_details",
        "args": {"lease_id": 1},
        "db_query": "SELECT l.id, l.space_name, l.landlord, l.monthly_rent, l.next_due, l.notes, "
        "(SELECT date_today FROM desk) AS desk_date_today FROM leases l WHERE l.id = ?",
        "db_params": (1,),
        "compare": lambda out, db: (
            {k: v for k, v in db[0].items() if k != "desk_date_today"} == out["lease"]
            and db[0]["desk_date_today"] == out["desk_date_today"]
        ),
    },
]


async def main() -> None:
    config = json.loads(MCP_JSON.read_text())
    server_name = next(iter(config["mcpServers"]))
    checksum_before = sha1(DB_PATH)

    results = []
    async with Client(config) as client:
        tools = [t.name for t in await client.list_tools()]
        for i, t in enumerate(TESTS, start=1):
            res = await client.call_tool(t["tool"], t["args"])
            output = res.structured_content
            db = db_rows(t["db_query"], t["db_params"])
            results.append(
                {
                    "test": i,
                    "ticket": t["ticket"],
                    "prompt": t["prompt"],
                    "tool": t["tool"],
                    "arguments": t["args"],
                    "tool_output": output,
                    "db_check": {"query": t["db_query"], "params": list(t["db_params"]), "rows": db},
                    "matches_db": bool(output.get("found")) and t["compare"](output, db),
                }
            )

    checksum_after = sha1(DB_PATH)
    report = {
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "connection": {
            "config_file": ".mcp.json",
            "server": server_name,
            "transport": "stdio",
            "client": "FastMCP Client launched from the .mcp.json mcpServers config",
        },
        "database": "data/campus_customs_new.db",
        "tools_listed": tools,
        "tests": results,
        "all_passed": all(r["matches_db"] for r in results),
        "database_unchanged": {
            "sha1_before": checksum_before,
            "sha1_after": checksum_after,
            "unchanged": checksum_before == checksum_after,
            "note": "All three tools are read-only, so no tool call updates the database.",
        },
    }
    OUT_PATH.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"tools": tools, "passed": [r["matches_db"] for r in results],
                      "db_unchanged": report["database_unchanged"]["unchanged"]}))


if __name__ == "__main__":
    asyncio.run(main())
