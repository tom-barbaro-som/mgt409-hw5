"""Command-line runner for the agent team (the FastAPI backend comes later).

From hw5:
  .venv/bin/python -m backend.run_tickets --ticket 101          # one ticket, current DB state
  .venv/bin/python -m backend.run_tickets --all                 # reset DB, then all open tickets
  .venv/bin/python -m backend.run_tickets --all --no-reset      # all open tickets, no reset
"""

from __future__ import annotations

import argparse
import asyncio
import json

from .audit import AuditTrail
from .config import AUDIT_TRAIL_PATH
from .db_reset import reset_working_db
from .team import OperationsTeam


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Campus Customs agent team.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ticket", type=int, action="append", help="Ticket id (repeatable).")
    group.add_argument("--all", action="store_true", help="Run every open ticket (resets the DB first).")
    parser.add_argument("--no-reset", action="store_true", help="With --all, skip the DB reset.")
    args = parser.parse_args()

    audit = AuditTrail(AUDIT_TRAIL_PATH)
    if args.all and not args.no_reset:
        print("Reset:", json.dumps(reset_working_db(audit)))

    async with OperationsTeam(audit=audit) as team:
        results = await team.run_open_tickets() if args.all else [await team.run_ticket(t) for t in args.ticket]
    for r in results:
        print(r.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
