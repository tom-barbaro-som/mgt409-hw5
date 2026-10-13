"""Accounting: cash, invoices, margins, and payment / PO / discount requests for human approval."""

from ..models import AgentReport
from .base import AgentSpec

SPEC = AgentSpec(
    name="accounting",
    title="Accountant",
    prompt_file="accounting.md",
    output_type=AgentReport,
    delegate_for="cash balance, invoices and overdue status, margins and discounts, payment/PO requests for human approval.",
)
