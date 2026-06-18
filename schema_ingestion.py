import sqlite3
import json
import os
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DATABASE_PATH", "data/sample.db")

# columns flagged as PHI/PII - blocked at planning stage
SENSITIVE_COLUMNS = {
    "customers": ["email"],
}

def ingest_schema() -> dict:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]

    schema = {}

    for table in tables:
        cursor.execute(f"PRAGMA table_info({table})")
        columns_info = cursor.fetchall()

        cursor.execute(f"SELECT * FROM {table} LIMIT 3")
        sample_rows = cursor.fetchall()
        col_names = [desc[0] for desc in cursor.description]

        columns = []
        for col in columns_info:
            col_name = col[1]
            col_type = col[2]
            is_sensitive = col_name in SENSITIVE_COLUMNS.get(table, [])
            columns.append({
                "name": col_name,
                "type": col_type,
                "sensitive": is_sensitive,
                "nullable": not col[3]
            })

        samples = []
        for row in sample_rows:
            row_dict = {}
            for i, val in enumerate(row):
                col_name = col_names[i]
                is_sensitive = col_name in SENSITIVE_COLUMNS.get(table, [])
                row_dict[col_name] = "***REDACTED***" if is_sensitive else val
            samples.append(row_dict)

        schema[table] = {
            "columns": columns,
            "sample_values": samples,
            "sensitive_columns": SENSITIVE_COLUMNS.get(table, [])
        }

    conn.close()
    return schema

def get_schema_for_llm(schema: dict, allowed_role: str = "analyst") -> dict:
    """Returns schema with sensitive columns stripped for LLM consumption."""
    safe_schema = {}
    for table, info in schema.items():
        safe_columns = [
            col for col in info["columns"]
            if not col["sensitive"]
        ]
        safe_schema[table] = {
            "columns": safe_columns,
            "sample_values": info["sample_values"]
        }
    return safe_schema

if __name__ == "__main__":
    schema = ingest_schema()
    print(json.dumps(schema, indent=2))
