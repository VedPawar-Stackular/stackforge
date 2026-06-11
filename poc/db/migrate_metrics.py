"""Apply the metrics migration: create stage1_metrics and add stage2_metrics.thinking_tokens.

Idempotent — safe to re-run. Mirrors migrate_stage2.py: splits the SQL file on
semicolons and executes each statement separately, since pg8000 does not support
multi-statement strings.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db import DB

SQL_PATH = os.path.join(os.path.dirname(__file__), "stage1_metrics.sql")

with open(SQL_PATH) as f:
    sql = f.read()


def _has_sql(stmt: str) -> bool:
    """Return True if stmt contains at least one non-comment, non-empty line."""
    for line in stmt.splitlines():
        line = line.strip()
        if line and not line.startswith("--"):
            return True
    return False


statements = [s.strip() for s in sql.split(";") if _has_sql(s)]

with DB() as db:
    for stmt in statements:
        db.execute(stmt)

print("Metrics migration applied successfully.")
print("  Table created:  stage1_metrics")
print("  Column ensured: stage2_metrics.thinking_tokens")
