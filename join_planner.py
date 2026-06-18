import yaml
from typing import List, Dict

with open("semantic_model/model.yaml", "r") as f:
    SEMANTIC_MODEL = yaml.safe_load(f)

def get_join_path(tables: List[str]) -> List[Dict]:
    """Returns approved join paths for the given tables."""
    if len(tables) <= 1:
        return []

    joins = SEMANTIC_MODEL.get("joins", [])
    needed_joins = []

    for join in joins:
        left = join["left_table"]
        right = join["right_table"]
        if left in tables and right in tables:
            needed_joins.append(join)

    return needed_joins

def format_joins_for_prompt(joins: List[Dict]) -> str:
    """Formats join paths as SQL JOIN clauses for the prompt."""
    if not joins:
        return "No joins required."

    lines = []
    for j in joins:
        lines.append(
            f"JOIN {j['right_table']} ON {j['left_table']}.{j['left_key']} = {j['right_table']}.{j['right_key']}"
        )
    return "\n".join(lines)

def validate_tables_exist(tables: List[str]) -> List[str]:
    """Returns only tables that exist in the semantic model."""
    known = set(SEMANTIC_MODEL.get("tables", {}).keys())
    return [t for t in tables if t in known]

if __name__ == "__main__":
    tables = ["orders", "customers", "products"]
    joins = get_join_path(tables)
    print(format_joins_for_prompt(joins))
