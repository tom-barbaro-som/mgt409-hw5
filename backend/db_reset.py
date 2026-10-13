"""Reset the working database (campus_customs_new.db) to the untouched original."""

from __future__ import annotations

import hashlib
import shutil

from .audit import AuditTrail
from .config import DB_ORIGINAL, DB_WORKING


def _sha1(path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def reset_working_db(audit: AuditTrail | None = None) -> dict:
    """Copy the original over the working copy (the original is only read) and verify it."""
    for suffix in ("-wal", "-shm", "-journal"):
        side = DB_WORKING.with_name(DB_WORKING.name + suffix)
        if side.exists():
            side.unlink()
    shutil.copy2(DB_ORIGINAL, DB_WORKING)
    result = {"original": DB_ORIGINAL.name, "working": DB_WORKING.name,
              "sha1": _sha1(DB_WORKING), "matches_original": _sha1(DB_WORKING) == _sha1(DB_ORIGINAL)}
    if audit:
        audit.append("db_reset", agent="system", reasoning="Working DB reset to original before a run.", detail=result)
    return result
