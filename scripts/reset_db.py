"""Reset data/campus_customs_new.db to the original data/campus_customs.db.

Run from hw5:  .venv/bin/python scripts/reset_db.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.audit import AuditTrail  # noqa: E402
from backend.config import AUDIT_TRAIL_PATH  # noqa: E402
from backend.db_reset import reset_working_db  # noqa: E402

if __name__ == "__main__":
    print(json.dumps(reset_working_db(AuditTrail(AUDIT_TRAIL_PATH)), indent=2))
