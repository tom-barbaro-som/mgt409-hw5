"""Shared agent builder: prompt loading, role-filtered MCP tools, and delegation."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models import Model

from ..config import MAX_DELEGATEES_PER_AGENT, MAX_DELEGATION_DEPTH, MAX_DELEGATIONS_PER_TICKET, PROMPTS_DIR, model_settings
from ..mcp_client import ROLE_TOOLS, role_toolset
from ..models import AgentDeps, AgentName

SHOP_RULES_FILE = "shop_rules.md"


@dataclass(frozen=True)
class AgentSpec:
    name: AgentName
    title: str
    prompt_file: str
    output_type: type[BaseModel]
    delegate_for: str  # one line other agents see when deciding whom to delegate to


def _read_prompt(file_name: str) -> str:
    return (PROMPTS_DIR / file_name).read_text(encoding="utf-8").strip()


def roster_text(specs: list[AgentSpec]) -> str:
    lines = ["## Your team (full connectivity: you may delegate to any of these agents)"]
    for s in specs:
        lines.append(f"- `{s.name}` ({s.title}): {s.delegate_for}")
    return "\n".join(lines)


def build_agent(spec: AgentSpec, model: Model, shop: MCPToolset, specs: list[AgentSpec]) -> Agent:
    instructions = "\n\n".join([
        _read_prompt(SHOP_RULES_FILE),
        roster_text(specs),
        _read_prompt(spec.prompt_file),
        "## Your MCP tools\n" + ", ".join(sorted(ROLE_TOOLS[spec.name]))
        + ", plus `delegate_task` for handing work to a teammate.",
    ])
    agent = Agent(
        model,
        name=spec.name,
        deps_type=AgentDeps,
        output_type=spec.output_type,
        instructions=instructions,
        toolsets=[role_toolset(shop, spec.name)],
        model_settings=model_settings(),
        retries=2,
    )

    @agent.instructions
    def run_context(ctx: RunContext[AgentDeps]) -> str:
        d = ctx.deps
        return (
            f"## This run\nYou are `{d.agent}`. Ticket: {d.run.ticket_id}. "
            f"Delegation chain: {' -> '.join(d.chain)} (depth {d.depth}/{MAX_DELEGATION_DEPTH}). "
            f"Delegations used on this ticket: {d.run.delegations}/{MAX_DELEGATIONS_PER_TICKET}. "
            f"Agents you have delegated to: {sorted(d.run.delegatees.get(d.agent, set())) or 'none'} "
            f"(max {MAX_DELEGATEES_PER_AGENT}). "
            f"Token budget for the whole ticket: {d.run.token_budget:,}; be economical."
        )

    # sequential=True: delegations run one at a time, never fanned out in parallel.
    @agent.tool(sequential=True)
    async def delegate_task(ctx: RunContext[AgentDeps], to_agent: AgentName, task: str, reason: str) -> dict:
        """Hand a specific sub-task to another agent and wait for its structured report.

        Use this when the work belongs to another agent's role. Give a precise task
        (ticket id, SKUs, sizes, quantities, ids, and what you need back) and a one-line
        reason for the audit trail. Delegate to one agent at a time and wait for its report.
        You may use at most two different agents per ticket, you cannot delegate to yourself,
        and depth and count limits apply.

        Args:
            to_agent: boss, inventory, accounting, facilities, or customer_service.
            task: Exactly what you need done and returned.
            reason: Why this agent, why now (recorded in the audit trail).
        """
        return await ctx.deps.team.delegate(ctx, to_agent, task, reason)

    return agent
