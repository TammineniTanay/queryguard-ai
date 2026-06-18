from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "demo.db"
SEED_PATH = ROOT / "data" / "demo_seed.sql"


def main() -> None:
    sql = SEED_PATH.read_text()
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(sql)
    print(f"Seeded demo database at {DB_PATH}")


if __name__ == "__main__":
    main()
