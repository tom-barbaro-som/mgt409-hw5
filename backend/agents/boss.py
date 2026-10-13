"""Boss: reads each ticket, delegates to the right agents, and makes the final decision."""

from ..models import TicketDecision
from .base import AgentSpec

SPEC = AgentSpec(
    name="boss",
    title="Boss / operations manager",
    prompt_file="boss.md",
    output_type=TicketDecision,
    delegate_for="triage, priorities across tickets and cash, final decisions, ticket status changes.",
)
