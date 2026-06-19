from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class QueryIntent:
    metrics: List[str]
    dimensions: List[str]
    filters: List[str]
    needs_detail_rows: bool = False
    blocked_reason: Optional[str] = None
    raw_question: str = ""


class NlRouter:
    """
    Routes natural language to a QueryIntent.
    Dangerous queries are blocked before reaching the LLM.
    Everything else passes through with the raw question attached
    so the LLM in sql_generator can do the actual reasoning.
    """

    BLOCKED_TERMS = ["delete", "drop", "update", "insert", "alter", "truncate"]

    def route(self, question: str) -> QueryIntent:
        q = question.lower().strip()

        for term in self.BLOCKED_TERMS:
            if term in q:
                return QueryIntent(
                    metrics=[],
                    dimensions=[],
                    filters=[],
                    blocked_reason="Only read-only analytics questions are allowed.",
                    raw_question=question
                )

        return QueryIntent(
            metrics=[],
            dimensions=[],
            filters=[],
            raw_question=question
        )
