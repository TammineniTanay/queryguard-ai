from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set

import yaml


@dataclass(frozen=True)
class ColumnRef:
    table: str
    column: str
    alias: str
    tags: Set[str]


class Catalog:
    def __init__(self, path: str | Path = "data/catalog.yml") -> None:
        self.path = Path(path)
        self.raw: Dict[str, Any] = yaml.safe_load(self.path.read_text())
        self.tables: Dict[str, Any] = self.raw["tables"]
        self.joins: List[Dict[str, str]] = self.raw.get("joins", [])
        self.metrics: Dict[str, Any] = self.raw.get("metrics", {})
        self.dimensions: Dict[str, Any] = self.raw.get("dimensions", {})
        self.roles: Dict[str, Any] = self.raw.get("roles", {})

    def table_alias(self, table: str) -> str:
        return self.tables[table]["alias"]

    def allowed_table_names(self) -> Set[str]:
        return set(self.tables.keys())

    def allowed_aliases(self) -> Set[str]:
        return {meta["alias"] for meta in self.tables.values()}

    def columns_for_table(self, table: str) -> Dict[str, Any]:
        return self.tables[table]["columns"]

    def all_columns(self) -> List[ColumnRef]:
        refs: List[ColumnRef] = []
        for table, meta in self.tables.items():
            alias = meta["alias"]
            for col, cmeta in meta["columns"].items():
                refs.append(ColumnRef(table=table, column=col, alias=alias, tags=set(cmeta.get("tags", []))))
        return refs

    def column_tags_by_qualified_name(self) -> Dict[str, Set[str]]:
        result: Dict[str, Set[str]] = {}
        for ref in self.all_columns():
            result[f"{ref.alias}.{ref.column}"] = ref.tags
            result[f"{ref.table}.{ref.column}"] = ref.tags
            result[ref.column] = ref.tags
        for name, meta in self.dimensions.items():
            result[name] = set(meta.get("tags", []))
            result[meta["expression"]] = set(meta.get("tags", []))
        return result

    def required_tables_for(self, metrics: Iterable[str], dimensions: Iterable[str]) -> Set[str]:
        tables: Set[str] = set()
        for metric in metrics:
            tables.update(self.metrics[metric].get("tables", []))
        for dimension in dimensions:
            tables.update(self.dimensions[dimension].get("tables", []))
        return tables

    def join_path_sql(self, required_tables: Set[str]) -> str:
        """Build deterministic FROM/JOIN clause from explicit catalog joins.

        MVP assumption: fact table is claims. This is intentional for demo reliability;
        production version should use graph shortest paths for arbitrary schemas.
        """
        if not required_tables:
            required_tables = {"claims"}
        base = "claims"
        if base not in required_tables:
            # Most governed analytic questions still join through claims in this demo.
            required_tables.add(base)

        sql = f"FROM claims c"
        joined = {base}
        for join in self.joins:
            left = join["left_table"]
            right = join["right_table"]
            if left in joined and right in required_tables:
                l_alias = self.table_alias(left)
                r_alias = self.table_alias(right)
                sql += f"\nJOIN {right} {r_alias} ON {l_alias}.{join['left_column']} = {r_alias}.{join['right_column']}"
                joined.add(right)
        missing = required_tables - joined
        if missing:
            raise ValueError(f"No approved join path found for tables: {sorted(missing)}")
        return sql

    def describe_for_prompt(self) -> str:
        lines = []
        for table, meta in self.tables.items():
            cols = ", ".join(meta["columns"].keys())
            lines.append(f"{table} ({meta['alias']}): {cols}")
        return "\n".join(lines)
