"""Apply Stage 3 ADO columns migration (ado_work_item_id, ado_work_item_url, ado_iteration_path)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db import DB

_SQL = """
ALTER TABLE sprints
  ADD COLUMN IF NOT EXISTS ado_work_item_id   INTEGER,
  ADD COLUMN IF NOT EXISTS ado_work_item_url  TEXT,
  ADD COLUMN IF NOT EXISTS ado_iteration_path TEXT;

ALTER TABLE tasks
  ADD COLUMN IF NOT EXISTS ado_work_item_id  INTEGER,
  ADD COLUMN IF NOT EXISTS ado_work_item_url TEXT;
"""

statements = [s.strip() for s in _SQL.split(";") if s.strip() and not s.strip().startswith("--")]

with DB() as db:
    for stmt in statements:
        db.execute(stmt)

print("Stage 3 ADO migration applied successfully.")
print("  sprints: +ado_work_item_id, +ado_work_item_url, +ado_iteration_path")
print("  tasks:   +ado_work_item_id, +ado_work_item_url")
