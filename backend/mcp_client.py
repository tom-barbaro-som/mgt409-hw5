"""Connects the agents to the Campus Customs MCP server (the only shop-data layer).

The connection comes from hw5/.mcp.json, the same config Claude Code uses.
Every agent tool call passes through `_guard_tool_call`, which:
  1. blocks any tool the calling agent's role is not allowed to use
     (human-only approve/reject and the system tool are never allowed),
  2. stamps the caller's real agent name onto identity arguments so an
     agent cannot file requests as someone else, and
  3. writes the call and its result to the audit trail.
"""

from __future__ import annotations

import json
import os
from typing import Any

from fastmcp import Client
from pydantic_ai import RunContext
from pydantic_ai.mcp import MCPToolset

from .audit import AuditTrail
from .config import MCP_CONFIG_PATH
from .models import AgentDeps

READ_TOOLS = frozenset({
    "check_inventory", "get_invoice_status", "get_lease_details", "list_tickets", "get_ticket",
    "get_cash_balance", "list_vendors", "list_invoices", "get_pricing", "list_approval_requests",
    "list_payments",
})
HUMAN_ONLY_TOOLS = frozenset({"approve_request", "reject_request"})
SYSTEM_TOOLS = frozenset({"request_budget_extension"})

# Default-deny: an agent sees only the tools listed for its role.
ROLE_TOOLS: dict[str, frozenset[str]] = {
    "boss": READ_TOOLS | {"add_ticket_note", "set_ticket_status"},
    "inventory": READ_TOOLS | {"add_ticket_note", "draft_purchase_order"},
    "accounting": READ_TOOLS | {"add_ticket_note", "request_payment", "request_price_override",
                                "draft_purchase_order"},
    "facilities": READ_TOOLS | {"add_ticket_note"},
    "customer_service": READ_TOOLS | {"add_ticket_note", "draft_message"},
}

# Tool argument that carries the caller's identity; always overwritten with the real caller.
IDENTITY_ARGS = {
    "add_ticket_note": "agent",
    "set_ticket_status": "agent",
    "request_payment": "requested_by",
    "draft_purchase_order": "requested_by",
    "request_price_override": "requested_by",
    "draft_message": "drafted_by",
}


def load_mcp_config() -> dict[str, Any]:
    """Read .mcp.json (paths relative to hw5/, so any clone works from any folder).

    CAMPUS_DB_PATH in the backend's environment overrides the DB (tests only).
    """
    config = json.loads(MCP_CONFIG_PATH.read_text())
    root = MCP_CONFIG_PATH.parent
    override = os.environ.get("CAMPUS_DB_PATH")
    for server in config["mcpServers"].values():
        server["cwd"] = str(root)
        command = root / server["command"]
        if command.exists():
            server["command"] = str(command)
        server["args"] = [str(root / a) if (root / a).exists() else a for a in server.get("args", [])]
        if override:
            server.setdefault("env", {})["CAMPUS_DB_PATH"] = override
    return config


def build_shop_toolset(audit: AuditTrail) -> MCPToolset:
    """One MCP connection shared by all agents; each agent gets a role-filtered view."""

    async def _guard_tool_call(ctx: RunContext[AgentDeps], call_tool, name: str, args: dict[str, Any]) -> Any:
        deps = ctx.deps
        common = dict(run_id=deps.run.run_id, ticket_id=deps.run.ticket_id, agent=deps.agent, depth=deps.depth)
        if name not in ROLE_TOOLS[deps.agent] or name in HUMAN_ONLY_TOOLS | SYSTEM_TOOLS:
            audit.append("tool_blocked", **common, detail={"tool": name, "args": args})
            return {"ok": False, "error": f"Tool '{name}' is not permitted for agent '{deps.agent}'."}
        if name in IDENTITY_ARGS:
            args = {**args, IDENTITY_ARGS[name]: deps.agent}
        step = deps.run.next_step()
        audit.append("tool_call", **common, step=step, detail={"tool": name, "args": args})
        result = await call_tool(name, args)
        audit.append("tool_result", **common, step=step, detail={"tool": name, "result": result})
        return result

    client = Client(load_mcp_config())
    return MCPToolset(client, id="campus-customs", process_tool_call=_guard_tool_call, max_retries=1)


def role_toolset(shop: MCPToolset, agent_name: str):
    allowed = ROLE_TOOLS[agent_name]
    return shop.filtered(lambda ctx, tool_def: tool_def.name in allowed)
