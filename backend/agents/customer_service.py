"""Customer Service: drafts every outward message; nothing is sent without a human."""

from ..models import AgentReport
from .base import AgentSpec

SPEC = AgentSpec(
    name="customer_service",
    title="Customer service lead",
    prompt_file="customer_service.md",
    output_type=AgentReport,
    delegate_for="drafting (never sending) replies to customers, student groups, landlords, and vendors.",
)
