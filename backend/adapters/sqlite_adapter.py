from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Tuple


class SQLiteAdapter:
    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = Path(db_path or os.getenv("SQLITE_DB_PATH", "data/demo.db"))

    def execute(self, sql: str) -> Tuple[List[str], List[Dict[str, Any]]]:
        if not self.db_path.exists():
            raise FileNotFoundError(f"Demo database not found at {self.db_path}. Run scripts/seed_demo_db.py first.")
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(sql)
            rows = [dict(row) for row in cur.fetchall()]
            columns = [desc[0] for desc in cur.description]
            return columns, rows
