from __future__ import annotations

from typing import List, Set

import sqlglot
from sqlglot import expressions as exp

from backend.core.catalog import Catalog
from backend.models.schemas import ValidationResult


class SqlValidator:
    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog
        self.allowed_tables: Set[str] = catalog.allowed_table_names()
        self.allowed_aliases: Set[str] = catalog.allowed_aliases()

    def validate(self, sql: str) -> ValidationResult:
        errors: List[str] = []
        warnings: List[str] = []
        try:
            parsed = sqlglot.parse_one(sql, read="sqlite")
        except Exception as exc:  # noqa: BLE001
            return ValidationResult(ok=False, errors=[f"SQL parse failed: {exc}"])

        if not isinstance(parsed, exp.Select):
            errors.append("Only SELECT queries are allowed.")

        if list(parsed.find_all(exp.Star)):
            errors.append("SELECT * is not allowed. Select explicit governed columns only.")

        dangerous_classes = [
            getattr(exp, name)
            for name in ["Delete", "Drop", "Update", "Insert", "Create", "Alter"]
            if hasattr(exp, name)
        ]
        dangerous = tuple(dangerous_classes)
        for node in parsed.walk():
            if dangerous and isinstance(node, dangerous):
                errors.append(f"Unsafe SQL operation blocked: {node.key}")

        for table in parsed.find_all(exp.Table):
            table_name = table.name
            if table_name not in self.allowed_tables:
                errors.append(f"Unknown or unapproved table: {table_name}")

        if not parsed.args.get("limit"):
            warnings.append("No LIMIT found; production policy should add one automatically.")

        return ValidationResult(ok=not errors, errors=errors, warnings=warnings)
