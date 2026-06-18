import re

FORBIDDEN = ["DELETE", "UPDATE", "INSERT", "DROP", "ALTER", "TRUNCATE", "CREATE"]


def clean_sql(raw):
    # strip markdown code fences if LLM wrapped the SQL
    raw = raw.strip()
    raw = re.sub(r"```sql|```", "", raw, flags=re.IGNORECASE)
    return raw.strip()


def validate_sql(sql, schema):
    """
    Returns (is_valid, reason).
    Blocks dangerous keywords, SELECT *, and unknown tables.
    """
    if not sql or sql.strip().upper() == "CANNOT_ANSWER":
        return False, "CANNOT_ANSWER"

    upper = sql.upper()

    for keyword in FORBIDDEN:
        if re.search(rf"\b{keyword}\b", upper):
            return False, f"Blocked: SQL contains '{keyword}'"

    if re.search(r"SELECT\s+\*", upper):
        return False, "Blocked: SELECT * is not allowed"

    # check all referenced tables actually exist
    found_tables = re.findall(r"\bFROM\s+(\w+)|\bJOIN\s+(\w+)", upper)
    referenced = {t for pair in found_tables for t in pair if t}
    known = {t.upper() for t in schema.keys()}
    unknown = referenced - known
    if unknown:
        return False, f"Blocked: Unknown tables referenced: {unknown}"

    return True, "OK"
