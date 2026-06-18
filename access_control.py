from typing import Dict, List
from app.schema_ingestion import ingest_schema

# role definitions - analyst cannot see PII
ROLES = {
    "analyst": {
        "blocked_columns": {"customers": ["email"]},
        "allowed_tables": ["orders", "products", "customers", "reviews"]
    },
    "admin": {
        "blocked_columns": {},
        "allowed_tables": ["orders", "products", "customers", "reviews"]
    }
}

def get_permissions(role: str) -> Dict:
    return ROLES.get(role, ROLES["analyst"])

def filter_schema_by_role(role: str) -> Dict:
    """Returns schema with sensitive columns stripped based on role."""
    schema = ingest_schema()
    permissions = get_permissions(role)
    blocked = permissions.get("blocked_columns", {})
    allowed_tables = permissions.get("allowed_tables", [])

    filtered = {}
    for table, info in schema.items():
        if table not in allowed_tables:
            continue
        blocked_cols = blocked.get(table, [])
        safe_columns = [
            col for col in info["columns"]
            if col["name"] not in blocked_cols
        ]
        filtered[table] = {
            "columns": safe_columns,
            "sample_values": info["sample_values"],
            "sensitive_columns": blocked_cols
        }
    return filtered

def check_sql_against_permissions(sql: str, role: str) -> tuple[bool, str]:
    """Checks if generated SQL uses any blocked columns."""
    permissions = get_permissions(role)
    blocked = permissions.get("blocked_columns", {})

    sql_lower = sql.lower()
    for table, cols in blocked.items():
        for col in cols:
            if col.lower() in sql_lower:
                return False, f"ACCESS DENIED: Column '{table}.{col}' is restricted for role '{role}'"

    return True, "OK"
