"""The five Campus Customs agents. Each file defines one agent's spec."""

from .accounting import SPEC as ACCOUNTING
from .base import AgentSpec, build_agent
from .boss import SPEC as BOSS
from .customer_service import SPEC as CUSTOMER_SERVICE
from .facilities import SPEC as FACILITIES
from .inventory import SPEC as INVENTORY

ALL_SPECS: list[AgentSpec] = [BOSS, INVENTORY, ACCOUNTING, FACILITIES, CUSTOMER_SERVICE]

__all__ = ["ALL_SPECS", "AgentSpec", "build_agent"]
