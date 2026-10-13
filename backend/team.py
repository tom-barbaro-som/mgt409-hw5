"""The Campus Customs operations team: agent loops, delegation, budgets, and audit.

Flow for one ticket:
  run_ticket(id) -> Boss agent loop (model -> MCP tools -> model ...)
                     |- delegate_task(to_agent, task, reason)  (any agent -> any agent)
                     |     -> that agent's own loop, sharing the ticket's usage/budget
                     '- TicketDecision
Every model step, tool call/result, delegation, and final report is appended to
output/audit_trail.json. If the ticket's token/request budget is exhausted the
run pauses and a budget_extension request is filed for a human to approve.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic_ai import Agent, RunContext, UsageLimits
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import ModelResponse, TextPart, ThinkingPart, ToolCallPart
from pydantic_ai.models import Model
from pydantic_ai.usage import RunUsage

from .agents import ALL_SPECS, build_agent
from .audit import AuditTrail
from .config import (
    AUDIT_TRAIL_PATH,
    BUDGET_EXTENSION_TOKENS,
    MAX_DELEGATEES_PER_AGENT,
    MAX_DELEGATION_DEPTH,
    MAX_DELEGATIONS_PER_TICKET,
    MAX_TICKETS_PER_RUN,
    TICKET_REQUEST_LIMIT,
    TICKET_TOKEN_BUDGET,
    TICKET_TOOL_CALL_LIMIT,
    build_model,
)
from .mcp_client import build_shop_toolset
from .models import AgentDeps, AgentName, TicketRunResult, TicketRunState, UsageSummary


def usage_summary(usage: RunUsage) -> UsageSummary:
    return UsageSummary(
        requests=usage.requests,
        tool_calls=usage.tool_calls,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
    )


class OperationsTeam:
    """Owns the shared MCP connection and the five agents. Use as an async context manager."""

    def __init__(self, model: Model | None = None, audit: AuditTrail | None = None):
        self.audit = audit or AuditTrail(AUDIT_TRAIL_PATH)
        self.shop = build_shop_toolset(self.audit)
        self._model = model
        self._agents: dict[str, Agent] | None = None

    @property
    def agents(self) -> dict[str, Agent]:
        """Built on first use, so MCP-only callers (dashboard reads, approvals) never need the model."""
        if self._agents is None:
            self._model = self._model or build_model()
            self._agents = {s.name: build_agent(s, self._model, self.shop, ALL_SPECS) for s in ALL_SPECS}
        return self._agents

    async def __aenter__(self) -> "OperationsTeam":
        await self.shop.__aenter__()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.shop.__aexit__(*exc)

    # ------------------------------------------------------------------ #
    async def call_shop_tool(self, name: str, args: dict[str, Any]) -> Any:
        """System-level MCP call (bypasses agent role checks; never used by agents)."""
        return await self.shop.direct_call_tool(name, args)

    @staticmethod
    def _limits(run: TicketRunState) -> UsageLimits:
        # Approved budget extensions scale request/tool-call limits along with tokens.
        scale = max(run.token_budget / TICKET_TOKEN_BUDGET, 1.0)
        return UsageLimits(
            request_limit=int(TICKET_REQUEST_LIMIT * scale),
            tool_calls_limit=int(TICKET_TOOL_CALL_LIMIT * scale),
            total_tokens_limit=run.token_budget,
        )

    def _log_model_step(self, response: ModelResponse, deps: AgentDeps, usage: RunUsage) -> None:
        texts = [p.content for p in response.parts if isinstance(p, TextPart) and p.content.strip()]
        thoughts = [p.content for p in response.parts if isinstance(p, ThinkingPart) and p.content]
        calls = [
            {"tool": p.tool_name, "args": p.args_as_dict()}
            for p in response.parts
            if isinstance(p, ToolCallPart)
        ]
        names = [c["tool"] for c in calls]
        if thoughts or texts:
            reasoning = " ".join(thoughts + texts)
        elif names == ["final_result"]:
            reasoning = "Finished; returning structured report."
        else:
            reasoning = f"Decided to call: {', '.join(names)}." if names else "No tool calls."
        self.audit.append(
            "model_step",
            run_id=deps.run.run_id,
            ticket_id=deps.run.ticket_id,
            agent=deps.agent,
            depth=deps.depth,
            step=deps.run.next_step(),
            reasoning=reasoning,
            detail={"planned_tool_calls": calls, "usage_so_far": usage_summary(usage).model_dump()},
        )

    async def run_agent(self, name: AgentName, task: str, deps: AgentDeps, usage: RunUsage) -> Any:
        """One agent loop, logging every step to the audit trail."""
        agent = self.agents[name]
        deps.run.agents_used.add(name)
        common = dict(run_id=deps.run.run_id, ticket_id=deps.run.ticket_id, agent=name, depth=deps.depth)
        source = deps.chain[-2] if len(deps.chain) > 1 else "system"
        self.audit.append("agent_started", **common, reasoning=f"Task received from {source}.", detail={"task": task})
        async with agent.iter(task, deps=deps, usage=usage, usage_limits=self._limits(deps.run)) as run:
            async for node in run:
                if Agent.is_call_tools_node(node):
                    self._log_model_step(node.model_response, deps, usage)
            output = run.result.output
        self.audit.append(
            "agent_finished",
            **common,
            reasoning=getattr(output, "reasoning", None),
            detail={"output": output.model_dump(), "usage_so_far": usage_summary(usage).model_dump()},
        )
        return output

    async def delegate(self, ctx: RunContext[AgentDeps], to_agent: str, task: str, reason: str) -> dict[str, Any]:
        """Full connectivity with guardrails: no self/cycle delegation, depth and count caps."""
        deps, run = ctx.deps, ctx.deps.run
        common = dict(run_id=run.run_id, ticket_id=run.ticket_id, agent=deps.agent, depth=deps.depth)
        key = (deps.agent, to_agent, " ".join(task.lower().split()))
        error = None
        if to_agent not in self.agents:
            error = f"Unknown agent '{to_agent}'."
        elif to_agent == deps.agent:
            error = "You cannot delegate to yourself."
        elif to_agent in deps.chain:
            error = (f"'{to_agent}' is already waiting on this chain ({' -> '.join(deps.chain)}). "
                     "Put your questions in your report instead.")
        elif deps.depth + 1 > MAX_DELEGATION_DEPTH:
            error = f"Delegation depth limit ({MAX_DELEGATION_DEPTH}) reached; finish with what you have."
        elif (to_agent not in run.delegatees.get(deps.agent, set())
              and len(run.delegatees.get(deps.agent, set())) >= MAX_DELEGATEES_PER_AGENT):
            used = sorted(run.delegatees[deps.agent])
            error = (f"You already delegated to {MAX_DELEGATEES_PER_AGENT} agents on this ticket ({', '.join(used)}). "
                     "Finish with their reports.")
        elif run.delegations >= MAX_DELEGATIONS_PER_TICKET:
            error = f"Delegation limit for this ticket ({MAX_DELEGATIONS_PER_TICKET}) reached."
        elif key in run.seen_delegations:
            error = "This exact task was already delegated on this ticket; use the earlier report."
        if error:
            self.audit.append("delegation_refused", **common, reasoning=reason,
                              detail={"to_agent": to_agent, "task": task, "error": error})
            return {"ok": False, "error": error}

        run.delegations += 1
        run.seen_delegations.add(key)
        run.delegatees.setdefault(deps.agent, set()).add(to_agent)
        self.audit.append("delegation", **common, step=run.next_step(), reasoning=reason,
                          detail={"from": deps.agent, "to_agent": to_agent, "task": task,
                                  "delegations_used": run.delegations})
        child = AgentDeps(agent=to_agent, run=run, team=self, depth=deps.depth + 1, chain=deps.chain + (to_agent,))
        prompt = f"Ticket {run.ticket_id}. Delegated to you by `{deps.agent}`.\nReason: {reason}\n\nTask:\n{task}"
        try:
            report = await self.run_agent(to_agent, prompt, child, usage=ctx.usage)
        except UsageLimitExceeded:
            raise  # budget stop must halt the whole ticket
        except Exception as exc:  # report failure to the delegator instead of crashing the ticket
            self.audit.append("error", **common, detail={"to_agent": to_agent, "error": f"{type(exc).__name__}: {exc}"})
            return {"ok": False, "error": f"{to_agent} failed: {type(exc).__name__}: {exc}"}
        return {"ok": True, "agent": to_agent, "report": report.model_dump()}

    # ------------------------------------------------------------------ #
    @staticmethod
    def new_run_id(ticket_id: int) -> str:
        return f"run-{ticket_id}-{uuid.uuid4().hex[:8]}"

    async def run_ticket(self, ticket_id: int, run_id: str | None = None) -> TicketRunResult:
        run_id = run_id or self.new_run_id(ticket_id)
        found = await self.call_shop_tool("get_ticket", {"ticket_id": ticket_id})
        if not found.get("found"):
            return TicketRunResult(run_id=run_id, ticket_id=ticket_id, outcome="skipped",
                                   token_budget=0, message=found.get("error"))
        status = found["ticket"]["status"]
        if status == "resolved":
            return TicketRunResult(run_id=run_id, ticket_id=ticket_id, outcome="skipped",
                                   token_budget=0, message="Ticket already resolved.")

        granted = await self.call_shop_tool(
            "list_approval_requests", {"status": "approved", "ticket_id": ticket_id, "kind": "budget_extension"}
        )
        extra = sum(int(r["payload"].get("tokens_requested", 0)) for r in granted["requests"])
        state = TicketRunState(run_id=run_id, ticket_id=ticket_id, token_budget=TICKET_TOKEN_BUDGET + extra)
        usage = RunUsage()
        self.audit.append("ticket_run_started", run_id=run_id, ticket_id=ticket_id, agent="system",
                          reasoning="Boss assigned the ticket.",
                          detail={"ticket_status": status, "token_budget": state.token_budget,
                                  "approved_extension_tokens": extra, "limits": self._limits(state).__dict__})

        deps = AgentDeps(agent="boss", run=state, team=self, depth=0, chain=("boss",))
        prompt = (f"Handle ticket {ticket_id}. Follow your procedure: read it, delegate as needed, "
                  "decide, record a note and status, and return your TicketDecision.")
        result = TicketRunResult(run_id=run_id, ticket_id=ticket_id, outcome="completed", token_budget=state.token_budget)
        try:
            result.decision = await self.run_agent("boss", prompt, deps, usage)
        except UsageLimitExceeded as exc:
            req = await self.call_shop_tool("request_budget_extension", {
                "ticket_id": ticket_id, "tokens_used": usage.total_tokens,
                "tokens_requested": BUDGET_EXTENSION_TOKENS, "requested_by": "system",
                "reason": f"Ticket run {run_id} stopped: {exc}. Approve to let the team continue.",
            })
            await self.call_shop_tool("add_ticket_note", {
                "ticket_id": ticket_id, "agent": "system",
                "note": f"Paused: AI budget reached. Budget request {req.get('approval_request_id')} awaits human approval.",
            })
            self.audit.append("budget_exceeded", run_id=run_id, ticket_id=ticket_id, agent="system",
                              reasoning="Token/request budget exhausted; pausing for human approval.",
                              detail={"error": str(exc), "budget_request": req})
            result.outcome = "paused_for_budget_approval"
            result.budget_request_id = req.get("approval_request_id")
            result.message = str(exc)
        except Exception as exc:
            self.audit.append("error", run_id=run_id, ticket_id=ticket_id, agent="system",
                              detail={"error": f"{type(exc).__name__}: {exc}"})
            result.outcome = "error"
            result.message = f"{type(exc).__name__}: {exc}"

        result.usage = usage_summary(usage)
        result.delegations = state.delegations
        self.audit.append("ticket_run_finished", run_id=run_id, ticket_id=ticket_id, agent="system",
                          reasoning=result.decision.decision if result.decision else result.message,
                          detail={"outcome": result.outcome, "usage": result.usage.model_dump(),
                                  "delegations": state.delegations, "agents_used": sorted(state.agents_used)})
        return result

    async def run_open_tickets(self, limit: int = MAX_TICKETS_PER_RUN) -> list[TicketRunResult]:
        """Run every open ticket in created order (capped). Reset the DB before a full run."""
        queue = await self.call_shop_tool("list_tickets", {"status": "open"})
        results = []
        for ticket in queue["tickets"][:limit]:
            results.append(await self.run_ticket(ticket["id"]))
        return results
