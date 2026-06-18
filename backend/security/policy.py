from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Tuple

from backend.core.catalog import Catalog


@dataclass
class PolicyDecision:
    allowed: bool
    sql: str
    reason: str = ""
    masked_fields: List[str] | None = None


class PolicyEngine:
    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog

    def apply(self, sql: str, role: str) -> PolicyDecision:
        role_policy = self.catalog.roles[role]
        deny_tags = set(role_policy.get("deny_tags", []))
        mask_tags = set(role_policy.get("mask_tags", []))
        tags_by_expr = self.catalog.column_tags_by_qualified_name()

        denied_hits: List[str] = []
        masked_fields: List[str] = []
        rewritten = sql

        # Check governed dimensions by alias name and expression.
        for dim_name, dim_meta in self.catalog.dimensions.items():
            tags = set(dim_meta.get("tags", []))
            expr = dim_meta["expression"]
            if tags & deny_tags and (re.search(rf"\b{re.escape(dim_name)}\b", sql) or expr in sql):
                denied_hits.append(dim_name)
            if tags & mask_tags and expr in rewritten:
                rewritten = rewritten.replace(expr, self._mask_expression(expr))
                masked_fields.append(dim_name)

        # Check raw column expressions.
        for expr, tags in tags_by_expr.items():
            # Only rewrite qualified column expressions here. Dimension aliases are handled above.
            if "." not in expr:
                continue
            if tags & deny_tags and re.search(rf"\b{re.escape(expr)}\b", sql):
                denied_hits.append(expr)
            if tags & mask_tags and re.search(rf"\b{re.escape(expr)}\b", rewritten):
                rewritten = re.sub(rf"\b{re.escape(expr)}\b", self._mask_expression(expr), rewritten)
                masked_fields.append(expr)

        if denied_hits:
            return PolicyDecision(
                allowed=False,
                sql=sql,
                reason=f"Role '{role}' is not allowed to access sensitive fields: {sorted(set(denied_hits))}",
                masked_fields=masked_fields,
            )

        row_filters = role_policy.get("row_filters", [])
        for row_filter in row_filters:
            rewritten = self._append_where(rewritten, row_filter)

        return PolicyDecision(True, rewritten, masked_fields=masked_fields)

    def _mask_expression(self, expr: str) -> str:
        # Portable SQLite demo masking. In BigQuery this can be replaced by policy tags/data masking.
        return f"('***MASKED***')"

    def _append_where(self, sql: str, condition: str) -> str:
        if re.search(r"\bWHERE\b", sql, flags=re.IGNORECASE):
            return re.sub(r"\bGROUP BY\b", f"AND {condition}\nGROUP BY", sql, flags=re.IGNORECASE)
        if re.search(r"\bGROUP BY\b", sql, flags=re.IGNORECASE):
            return re.sub(r"\bGROUP BY\b", f"WHERE {condition}\nGROUP BY", sql, flags=re.IGNORECASE)
        if re.search(r"\bORDER BY\b", sql, flags=re.IGNORECASE):
            return re.sub(r"\bORDER BY\b", f"WHERE {condition}\nORDER BY", sql, flags=re.IGNORECASE)
        if re.search(r"\bLIMIT\b", sql, flags=re.IGNORECASE):
            return re.sub(r"\bLIMIT\b", f"WHERE {condition}\nLIMIT", sql, flags=re.IGNORECASE)
        return sql + f"\nWHERE {condition}"
