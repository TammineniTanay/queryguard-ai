from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.adapters.sqlite_adapter import SQLiteAdapter
from backend.core.catalog import Catalog
from backend.core.explainer import Explainer
from backend.core.groundedness import check_groundedness
from backend.core.nl_router import NlRouter
from backend.core.sql_generator import SqlGenerator
from backend.core.sql_validator import SqlValidator
from backend.models.schemas import AskRequest, AskResponse, ValidationResult
from backend.security.audit import AuditLogger
from backend.security.policy import PolicyEngine

app = FastAPI(title="QueryGuard AI", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

catalog = Catalog()
router = NlRouter()
generator = SqlGenerator(catalog)
validator = SqlValidator(catalog)
policy = PolicyEngine(catalog)
explainer = Explainer()
audit = AuditLogger()


def get_adapter() -> Any:
    mode = os.getenv("QUERYGUARD_EXECUTION_MODE", "sqlite").lower()
    if mode == "bigquery":
        from backend.adapters.bigquery_adapter import BigQueryAdapter
        return BigQueryAdapter()
    return SQLiteAdapter()


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "version": "1.0.0"}


@app.get("/catalog")
def get_catalog() -> Dict[str, Any]:
    return {
        "tables": list(catalog.tables.keys()),
        "metrics": list(catalog.metrics.keys()),
        "dimensions": list(catalog.dimensions.keys()),
        "roles": list(catalog.roles.keys()),
    }


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    sql = ""
    safe_sql = ""

    try:
        intent = router.route(req.question)
        if intent.blocked_reason:
            audit_id = audit.log({
                "user_id": req.user_id,
                "role": req.role.value,
                "question": req.question,
                "blocked": True,
                "reason": intent.blocked_reason,
            })
            return AskResponse(
                question=req.question,
                role=req.role.value,
                sql="",
                safe_sql="",
                explanation="This question was blocked. Only read-only analytics are allowed.",
                validation=ValidationResult(ok=False, errors=[intent.blocked_reason]),
                columns=[],
                rows=[],
                audit_id=audit_id,
                blocked=True,
                block_reason=intent.blocked_reason,
            )

        sql = generator.generate(intent, limit=req.limit)

        if sql.strip().upper() == "CANNOT_ANSWER":
            audit_id = audit.log({
                "user_id": req.user_id,
                "role": req.role.value,
                "question": req.question,
                "blocked": True,
                "reason": "LLM could not answer with available schema",
            })
            return AskResponse(
                question=req.question,
                role=req.role.value,
                sql=sql,
                safe_sql="",
                explanation="This question cannot be answered with the available data.",
                validation=ValidationResult(ok=False, errors=["Schema insufficient to answer question"]),
                columns=[],
                rows=[],
                audit_id=audit_id,
                blocked=True,
                block_reason="Cannot answer with available schema.",
            )

        decision = policy.apply(sql, req.role.value)
        if not decision.allowed:
            audit_id = audit.log({
                "user_id": req.user_id,
                "role": req.role.value,
                "question": req.question,
                "sql": sql,
                "blocked": True,
                "reason": decision.reason,
            })
            return AskResponse(
                question=req.question,
                role=req.role.value,
                sql=sql,
                safe_sql=sql,
                explanation=decision.reason,
                validation=ValidationResult(ok=False, errors=[decision.reason]),
                columns=[],
                rows=[],
                audit_id=audit_id,
                blocked=True,
                block_reason=decision.reason,
            )

        safe_sql = decision.sql

        validation = validator.validate(safe_sql)
        if not validation.ok:
            audit_id = audit.log({
                "user_id": req.user_id,
                "role": req.role.value,
                "question": req.question,
                "sql": sql,
                "safe_sql": safe_sql,
                "blocked": True,
                "validation_errors": validation.errors,
            })
            return AskResponse(
                question=req.question,
                role=req.role.value,
                sql=sql,
                safe_sql=safe_sql,
                explanation="Generated SQL failed validation and was not executed.",
                validation=validation,
                columns=[],
                rows=[],
                audit_id=audit_id,
                blocked=True,
                block_reason="SQL validation failed.",
            )

        columns, rows = get_adapter().execute(safe_sql)

        ground = check_groundedness(req.question, safe_sql, rows)
        confidence = ground.get("confidence", 1.0)
        grounded = ground.get("grounded", True)

        explanation = explainer.explain(intent, decision.masked_fields or [])
        if not grounded or confidence < 0.6:
            explanation += f" Low confidence ({confidence:.0%}): {ground.get('reason', '')}"

        audit_id = audit.log({
            "user_id": req.user_id,
            "role": req.role.value,
            "question": req.question,
            "sql": sql,
            "safe_sql": safe_sql,
            "blocked": False,
            "row_count": len(rows),
            "confidence": confidence,
            "grounded": grounded,
        })

        return AskResponse(
            question=req.question,
            role=req.role.value,
            sql=sql,
            safe_sql=safe_sql,
            explanation=explanation,
            validation=validation,
            columns=columns,
            rows=rows,
            audit_id=audit_id,
        )

    except Exception as exc:
        audit_id = audit.log({
            "user_id": req.user_id,
            "role": req.role.value,
            "question": req.question,
            "sql": sql,
            "blocked": True,
            "exception": str(exc),
        })
        return AskResponse(
            question=req.question,
            role=req.role.value,
            sql=sql,
            safe_sql=safe_sql,
            explanation="The system could not safely answer this question.",
            validation=ValidationResult(ok=False, errors=[str(exc)]),
            columns=[],
            rows=[],
            audit_id=audit_id,
            blocked=True,
            block_reason=str(exc),
        )
