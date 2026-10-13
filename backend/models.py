"""Data types shared by the Campus Customs agent team."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

AgentName = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]
AGENT_NAMES: tuple[AgentName, ...] = ("boss", "inventory", "accounting", "facilities", "customer_service")

TicketStatus = Literal["open", "in_progress", "waiting_approval", "blocked", "resolved"]

AuditEvent = Literal[
    "db_reset",
    "ticket_run_started",
    "agent_started",
    "model_step",
    "tool_call",
    "tool_result",
    "tool_blocked",
    "delegation",
    "delegation_refused",
    "agent_finished",
    "budget_exceeded",
    "ticket_run_finished",
    "error",
    "human_decision",
    "ticket_resolved",
    "report_generated",
]


# --------------------------------------------------------------------------- #
# Structured agent outputs
# --------------------------------------------------------------------------- #
class AgentReport(BaseModel):
    """What a specialist agent hands back to whoever delegated to it."""

    agent: AgentName = Field(description="Your own agent name.")
    task_summary: str = Field(description="One sentence restating the task you were given.")
    findings: list[str] = Field(description="Facts found in the database (cite ids, SKUs, amounts, dates).")
    actions_taken: list[str] = Field(
        default_factory=list, description="Notes added, drafts created, requests filed (with approval ids)."
    )
    approval_request_ids: list[int] = Field(
        default_factory=list, description="Ids of approval requests you created or found pending."
    )
    blockers: list[str] = Field(default_factory=list, description="Anything preventing resolution.")
    recommendation: str = Field(description="What you recommend the Boss / human decide next.")
    reasoning: str = Field(description="Short explanation of why, for the audit trail.")
    needs_human: bool = Field(default=False, description="True if a human decision is required.")


class TicketDecision(BaseModel):
    """The Boss's final decision for one ticket."""

    ticket_id: int
    final_status: TicketStatus = Field(description="Status you set on the ticket (or would set).")
    decision: str = Field(description="The final decision in plain language.")
    reasoning: str = Field(description="Why, citing the facts the team found.")
    agents_consulted: list[AgentName] = Field(default_factory=list)
    approval_request_ids: list[int] = Field(
        default_factory=list, description="Every pending approval request a human must act on for this ticket."
    )
    draft_message_ids: list[int] = Field(default_factory=list, description="Approval ids of drafted messages.")
    next_steps_for_human: list[str] = Field(
        default_factory=list, description="Ordered list of what the manager should approve/decide, and why."
    )
    risks: list[str] = Field(default_factory=list, description="Cash, timing, or customer risks to flag.")


# --------------------------------------------------------------------------- #
# Run results and audit entries
# --------------------------------------------------------------------------- #
class UsageSummary(BaseModel):
    requests: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class TicketRunResult(BaseModel):
    run_id: str
    ticket_id: int
    outcome: Literal["completed", "paused_for_budget_approval", "skipped", "error"]
    decision: TicketDecision | None = None
    usage: UsageSummary = Field(default_factory=UsageSummary)
    token_budget: int
    delegations: int = 0
    budget_request_id: int | None = None
    message: str | None = None


class AuditEntry(BaseModel):
    """One line of output/audit_trail.json (JSON Lines, append-only)."""

    ts: str
    event: AuditEvent
    run_id: str | None = None
    ticket_id: int | None = None
    agent: AgentName | Literal["system"] | None = None
    depth: int | None = None
    step: int | None = None
    reasoning: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Run-time dependencies passed to every agent (PydanticAI deps)
# --------------------------------------------------------------------------- #
@dataclass
class TicketRunState:
    """Shared by every agent working on the same ticket run."""

    run_id: str
    ticket_id: int
    token_budget: int
    delegations: int = 0
    steps: int = 0
    seen_delegations: set[tuple[str, str, str]] = field(default_factory=set)
    agents_used: set[str] = field(default_factory=set)
    delegatees: dict[str, set[str]] = field(default_factory=dict)  # delegator -> agents it has used

    def next_step(self) -> int:
        self.steps += 1
        return self.steps


@dataclass
class AgentDeps:
    """Per-agent-run context: who is acting, how deep in the delegation chain, and the team."""

    agent: AgentName
    run: TicketRunState
    team: Any  # backend.team.OperationsTeam (Any avoids a circular import)
    depth: int = 0
    chain: tuple[str, ...] = ()


# --------------------------------------------------------------------------- #
# API request / response bodies (backend/main.py)
# --------------------------------------------------------------------------- #
class ApproveBody(BaseModel):
    approved_by: str = Field(min_length=1, description="Name of the human approving (agent names are refused).")
    note: str | None = None


class RejectBody(BaseModel):
    rejected_by: str = Field(min_length=1, description="Name of the human rejecting.")
    reason: str = Field(min_length=1)


class ResetBody(BaseModel):
    confirm: bool = Field(description="Must be true; resetting discards every change in the working DB.")


class RunJob(BaseModel):
    run_id: str
    ticket_id: int
    status: Literal["running", "completed", "paused_for_budget_approval", "skipped", "error"]
    started_at: str
    finished_at: str | None = None
    result: TicketRunResult | None = None
