"""Inventory: verifies stock by SKU/size, finds shortages, and picks a vendor to restock."""

from ..models import AgentReport
from .base import AgentSpec

SPEC = AgentSpec(
    name="inventory",
    title="Inventory manager",
    prompt_file="inventory.md",
    output_type=AgentReport,
    delegate_for="stock by SKU and size, shortages, which vendor can restock, lead times, drafting restock POs.",
)
