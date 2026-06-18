from __future__ import annotations

from backend.core.nl_router import QueryIntent


class Explainer:
    def explain(self, intent: QueryIntent, masked_fields: list[str] | None = None) -> str:
        metric_text = ", ".join(intent.metrics) if intent.metrics else "requested metrics"
        dim_text = ", ".join(intent.dimensions) if intent.dimensions else "no grouping"
        explanation = f"I answered using governed metrics ({metric_text}) grouped by {dim_text}."
        if intent.filters:
            explanation += " Applied filters: " + "; ".join(intent.filters) + "."
        if masked_fields:
            explanation += " Some sensitive fields were masked based on your role."
        return explanation
