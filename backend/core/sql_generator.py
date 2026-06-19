from __future__ import annotations

import os
import re
from dotenv import load_dotenv
from openai import OpenAI

from backend.core.catalog import Catalog
from backend.core.nl_router import QueryIntent

load_dotenv()

client = OpenAI(
    api_key=os.getenv("FEATHERLESS_API_KEY"),
    base_url=os.getenv("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1")
)

MODEL = os.getenv("FEATHERLESS_MODEL", "Qwen/Qwen2.5-72B-Instruct")


class SqlGenerator:
    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog

    def generate(self, intent: QueryIntent, limit: int = 100) -> str:
        if intent.blocked_reason:
            raise ValueError(intent.blocked_reason)

        system_prompt = self._build_system_prompt(limit)
        user_message = f"Question: {intent.raw_question}\n\nSQL:"

        return self._call_llm(system_prompt, user_message)

    def repair(self, intent: QueryIntent, failed_sql: str, errors: list[str], limit: int = 100) -> str:
        """
        Called when the first SQL attempt fails validation or execution.
        Gives the LLM one chance to fix it with the exact error in context,
        instead of the pipeline dead-ending on the first failure.
        """
        system_prompt = self._build_system_prompt(limit)
        error_text = "\n".join(f"- {e}" for e in errors)

        user_message = f"""Question: {intent.raw_question}

Your previous SQL attempt failed:
{failed_sql}

Errors:
{error_text}

Write a corrected SQL query that fixes these errors. Follow all the same rules.
If the question genuinely cannot be answered even after fixing the errors, write exactly: CANNOT_ANSWER

SQL:"""

        return self._call_llm(system_prompt, user_message)

    def _call_llm(self, system_prompt: str, user_message: str) -> str:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.0,
            max_tokens=512
        )
        sql = response.choices[0].message.content.strip()
        sql = re.sub(r"```sql|```", "", sql, flags=re.IGNORECASE).strip()
        return sql

    def _build_system_prompt(self, limit: int) -> str:
        schema_description = self.catalog.describe_for_prompt()
        join_info = self._describe_joins()
        metrics_info = self._describe_metrics()
        dimensions_info = self._describe_dimensions()

        return f"""You are a SQLite SQL expert. Generate accurate, safe SQL from a natural language question.

Rules:
- Only use the tables, columns, metrics, and joins listed below
- Never use SELECT *
- Never write DELETE, UPDATE, INSERT, DROP, ALTER, or TRUNCATE
- Always include LIMIT {limit}
- Use table aliases exactly as defined (e.g. claims = c, patients = p, departments = d)
- Write SQL for exactly what is asked, even if it touches sensitive fields like email or diagnosis.
  A separate access-control layer downstream will mask or block sensitive fields based on the
  user's role. Your job is only to translate the question into correct SQL, not to enforce permissions.
- If the question truly cannot be expressed with the tables/columns listed below, write exactly: CANNOT_ANSWER
- Return only the SQL query, no explanation, no markdown fences

Schema:
{schema_description}

Approved joins:
{join_info}

Available metrics (use these expressions):
{metrics_info}

Available dimensions (use these expressions):
{dimensions_info}"""

    def _describe_joins(self) -> str:
        lines = []
        for j in self.catalog.joins:
            left_alias = self.catalog.table_alias(j["left_table"])
            right_alias = self.catalog.table_alias(j["right_table"])
            lines.append(
                f"JOIN {j['right_table']} {right_alias} ON "
                f"{left_alias}.{j['left_column']} = {right_alias}.{j['right_column']}"
            )
        return "\n".join(lines) if lines else "No joins available."

    def _describe_metrics(self) -> str:
        lines = []
        for name, meta in self.catalog.metrics.items():
            lines.append(f"  {name}: {meta['expression']} - {meta['description']}")
        return "\n".join(lines)

    def _describe_dimensions(self) -> str:
        lines = []
        for name, meta in self.catalog.dimensions.items():
            tags = meta.get("tags", [])
            tag_note = " [SENSITIVE]" if tags else ""
            lines.append(f"  {name}: {meta['expression']}{tag_note}")
        return "\n".join(lines)
