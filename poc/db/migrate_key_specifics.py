"""
Migration: add key_specifics and status columns to the requirements table.

  key_specifics TEXT[] — verbatim measurements, time limits, field names, UI
                         details extracted alongside each requirement. Used to
                         carry specific client language through to story ACs.

  status TEXT          — 'active' (default) or 'duplicate' (set by cross-doc
                         dedup pass in runner.py). Stage 2 skips duplicates.

Run once from the poc/ directory:
    python db/migrate_key_specifics.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import DB  # noqa: E402

_MIGRATIONS = [
    (
        "key_specifics column",
        """
        ALTER TABLE requirements
            ADD COLUMN IF NOT EXISTS key_specifics TEXT[] DEFAULT '{}';
        """,
    ),
    (
        "status column",
        """
        ALTER TABLE requirements
            ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active';
        """,
    ),
]


def run() -> None:
    with DB() as db:
        for name, sql in _MIGRATIONS:
            print(f"  Applying: {name} ...", end=" ")
            db.execute(sql.strip())
            print("done")
    print("Migration complete.")


if __name__ == "__main__":
    run()
