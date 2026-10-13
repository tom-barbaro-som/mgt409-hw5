"""Facilities: the physical shop - leases, rent, landlord notices, space and maintenance."""

from ..models import AgentReport
from .base import AgentSpec

SPEC = AgentSpec(
    name="facilities",
    title="Facilities manager",
    prompt_file="facilities.md",
    output_type=AgentReport,
    delegate_for="leases, rent due dates, landlord notices, shop space, shelving/locations, maintenance.",
)
