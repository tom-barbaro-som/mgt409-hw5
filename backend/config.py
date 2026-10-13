"""Paths, model setup (gpt-6-luna via Portkey), and team guardrail limits."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
from pydantic_ai.providers.openai import OpenAIProvider

BACKEND_DIR = Path(__file__).resolve().parent
HW5_DIR = BACKEND_DIR.parent
PROMPTS_DIR = BACKEND_DIR / "prompts"
MCP_CONFIG_PATH = HW5_DIR / ".mcp.json"
DB_ORIGINAL = HW5_DIR / "data" / "campus_customs.db"
# CAMPUS_DB_PATH (tests only) redirects both the MCP server and the reset to another copy.
DB_WORKING = Path(os.environ.get("CAMPUS_DB_PATH", HW5_DIR / "data" / "campus_customs_new.db")).resolve()
AUDIT_TRAIL_PATH = Path(os.environ.get("AUDIT_TRAIL_PATH", HW5_DIR / "output" / "audit_trail.json"))

# Where PORTKEY_API_KEY is read from (the key itself is never in this project):
#   1. hw5/.env (copy .env.example; git-ignored)
#   2. the original class folder's Portkey.env, if this repo sits inside it (backend/ -> hw5/ -> Homework/ -> class folder)
_ENV_CANDIDATES = [HW5_DIR / ".env"] + ([BACKEND_DIR.parents[2] / "Portkey.env"] if len(BACKEND_DIR.parents) > 2 else [])
ENV_FILE = next((p for p in _ENV_CANDIDATES if p.exists()), _ENV_CANDIDATES[-1])
# Loads PORTKEY_API_KEY into the environment only; the value is never printed or logged.
load_dotenv(ENV_FILE, override=False)

PORTKEY_BASE_URL = os.environ.get("PORTKEY_BASE_URL", "https://api.portkey.ai/v1")
# This Portkey key has a default provider attached, so no provider header is needed.
PORTKEY_PROVIDER = os.environ.get("PORTKEY_PROVIDER", "")

# The project uses gpt-6-luna only. OPENAI_MODEL is kept as the one place the
# name lives, but any other value is rejected.
ALLOWED_MODELS = {"gpt-6-luna"}
MODEL_NAME = os.environ.get("OPENAI_MODEL", "gpt-6-luna")
REASONING_EFFORT = os.environ.get("OPENAI_REASONING_EFFORT", "low")


def _int_env(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


# ---- Token / loop guardrails (see output/harness.md "Safety") ---------------
TICKET_TOKEN_BUDGET = _int_env("TICKET_TOKEN_BUDGET", 150_000)        # all agents, one ticket
TICKET_REQUEST_LIMIT = _int_env("TICKET_REQUEST_LIMIT", 40)           # model calls, one ticket
TICKET_TOOL_CALL_LIMIT = _int_env("TICKET_TOOL_CALL_LIMIT", 80)       # tool calls, one ticket
BUDGET_EXTENSION_TOKENS = _int_env("BUDGET_EXTENSION_TOKENS", 75_000)  # asked of the human when paused
MAX_DELEGATION_DEPTH = _int_env("MAX_DELEGATION_DEPTH", 3)            # boss -> a -> b -> c
MAX_DELEGATIONS_PER_TICKET = _int_env("MAX_DELEGATIONS_PER_TICKET", 6)
MAX_DELEGATEES_PER_AGENT = _int_env("MAX_DELEGATEES_PER_AGENT", 2)     # distinct agents each agent may use per ticket
MAX_TICKETS_PER_RUN = _int_env("MAX_TICKETS_PER_RUN", 10)
MAX_OUTPUT_TOKENS = _int_env("MAX_OUTPUT_TOKENS", 4_000)              # per model response


class AgentNotConfiguredError(RuntimeError):
    """Raised when the Portkey key isn't available or the model isn't allowed."""


def build_model() -> OpenAIResponsesModel:
    """gpt-6-luna through Portkey's OpenAI-compatible gateway (Responses API)."""
    if MODEL_NAME not in ALLOWED_MODELS:
        raise AgentNotConfiguredError(f"Model '{MODEL_NAME}' is not allowed; this project uses gpt-6-luna only.")
    api_key = os.environ.get("PORTKEY_API_KEY")
    if not api_key:
        raise AgentNotConfiguredError("PORTKEY_API_KEY is not set. Copy .env.example to .env in hw5/ and add your key.")
    headers = {"x-portkey-api-key": api_key}
    if PORTKEY_PROVIDER:
        headers["x-portkey-provider"] = PORTKEY_PROVIDER
    client = AsyncOpenAI(api_key=api_key, base_url=PORTKEY_BASE_URL, default_headers=headers)
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))


def model_settings() -> OpenAIResponsesModelSettings:
    return OpenAIResponsesModelSettings(
        openai_reasoning_effort=REASONING_EFFORT,
        openai_reasoning_summary="concise",  # short reasoning summaries, recorded in the audit trail
        max_tokens=MAX_OUTPUT_TOKENS,
    )
