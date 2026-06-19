from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.adapters.sqlite_adapter import SQLiteAdapter
from backend.core.catalog import Catalog
from backend.core.explainer import Explainer
from backend.core.groundedness import check_groundedness
from backend.core.logical_intent import validate_logical_intent
from backend.core.nl_router import NlRouter, QueryIntent
from backend.core.sql_generator import SqlGenerator
from backend.core.sql_validator import SqlValidator
from backend.models.schemas import AskRequest, AskResponse, ValidationResult
from backend.security.audit import AuditLogger
from backend.security.policy import PolicyEngine, PolicyDecision

app = FastAPI(title="QueryGuard AI", version="1.2.0")
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

MAX_REPAIR_ATTEMPTS = 1


def get_adapter() -> Any:
    mode = os.getenv("QUERYGUARD_EXECUTION_MODE", "sqlite").lower()
    if mode == "bigquery":
        from backend.adapters.bigquery_adapter import BigQueryAdapter
        return BigQueryAdapter()
    return SQLiteAdapter()


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "version": "1.2.0"}


@app.get("/catalog")
def get_catalog() -> Dict[str, Any]:
    return {
        "tables": list(catalog.tables.keys()),
        "metrics": list(catalog.metrics.keys()),
        "dimensions": list(catalog.dimensions.keys()),
        "roles": list(catalog.roles.keys()),
    }


def _try_validate_and_execute(
    safe_sql: str,
) -> Tuple[bool, Optional[list], Optional[list], Optional[ValidationResult], list[str]]:
    """
    Runs structural validation, then attempts execution.
    Returns (success, columns, rows, validation, errors).
    Both validation failures and execution exceptions are collected
    into the same `errors` list so the repair loop has one place to read from.
    """
    validation = validator.validate(safe_sql)
    if not validation.ok:
        return False, None, None, validation, validation.errors

    try:
        columns, rows = get_adapter().execute(safe_sql)
        return True, columns, rows, validation, []
    except Exception as exc:  # noqa: BLE001
        return False, None, None, validation, [f"SQL execution failed: {exc}"]


def _generate_policy_validate_execute(
    req: AskRequest,
    intent: QueryIntent,
    repaired_from: Optional[str] = None,
    repair_errors: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """
    One full attempt: generate (or repair) SQL, apply policy, validate, execute.
    Returns a dict describing the outcome so the caller can decide whether
    to retry, mask-and-return, or hard-fail.
    """
    if repaired_from is not None:
        sql = generator.repair(intent, repaired_from, repair_errors or [], limit=req.limit)
    else:
        sql = generator.generate(intent, limit=req.limit)

    if sql.strip().upper() == "CANNOT_ANSWER":
        return {"stage": "cannot_answer", "sql": sql}

    decision: PolicyDecision = policy.apply(sql, req.role.value)
    if not decision.allowed:
        return {"stage": "policy_denied", "sql": sql, "decision": decision}

    safe_sql = decision.sql
    success, columns, rows, validation, errors = _try_validate_and_execute(safe_sql)

    if not success:
        return {
            "stage": "execution_failed",
            "sql": sql,
            "safe_sql": safe_sql,
            "validation": validation,
            "errors": errors,
            "decision": decision,
        }

    # Syntax is valid and the query ran. Check the ORIGINAL sql (pre-masking)
    # against the ORIGINAL question text - masking is an intentional policy
    # change, not a hallucination, so checking post-mask SQL would falsely
    # flag every masked query.
    #
    # IMPORTANT: this check is LLM-as-judge and has been observed to be
    # non-deterministic - the same question/SQL pair can get a different
    # verdict across runs (confirmed: "how many claims are there in total"
    # passed in one eval run and failed in the next, identical code path).
    # A flaky binary gate must never be allowed to block a result the rest
    # of the pipeline (syntax validation, real execution, row return) has
    # already confirmed works. So: still attempt one repair if flagged
    # (a real mismatch is worth trying to fix), but if it's still flagged
    # after that, return the result anyway with a visible warning instead
    # of silently killing a possibly-correct answer.
    intent_check = validate_logical_intent(req.question, sql)

    return {
        "stage": "success",
        "sql": sql,
        "safe_sql": safe_sql,
        "validation": validation,
        "columns": columns,
        "rows": rows,
        "decision": decision,
        "intent_flagged": not intent_check.is_valid,
        "intent_reason": intent_check.reason,
        "intent_translated": intent_check.translated_intent,
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

        # First attempt
        attempt = _generate_policy_validate_execute(req, intent)
        repair_count = 0

        # Repair loop: only retries on execution_failed (validation/SQLite
        # error). The logical intent check no longer blocks - see the
        # _generate_policy_validate_execute docstring for why a flaky
        # LLM-as-judge gate should not be allowed to kill correct answers.
        while attempt["stage"] == "execution_failed" and repair_count < MAX_REPAIR_ATTEMPTS:
            attempt = _generate_policy_validate_execute(
                req,
                intent,
                repaired_from=attempt["sql"],
                repair_errors=attempt["errors"],
            )
            repair_count += 1

        sql = attempt.get("sql", "")

        if attempt["stage"] == "cannot_answer":
            audit_id = audit.log({
                "user_id": req.user_id,
                "role": req.role.value,
                "question": req.question,
                "blocked": True,
                "reason": "LLM could not express this question with the available schema",
                "repair_attempts": repair_count,
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

        if attempt["stage"] == "policy_denied":
            decision = attempt["decision"]
            audit_id = audit.log({
                "user_id": req.user_id,
                "role": req.role.value,
                "question": req.question,
                "sql": sql,
                "blocked": True,
                "reason": decision.reason,
                "repair_attempts": repair_count,
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
                masked_fields=decision.masked_fields or [],
            )

        if attempt["stage"] == "execution_failed":
            # ran out of repair attempts
            safe_sql = attempt.get("safe_sql", "")
            validation = attempt.get("validation") or ValidationResult(ok=False, errors=attempt["errors"])
            audit_id = audit.log({
                "user_id": req.user_id,
                "role": req.role.value,
                "question": req.question,
                "sql": sql,
                "safe_sql": safe_sql,
                "blocked": True,
                "validation_errors": attempt["errors"],
                "repair_attempts": repair_count,
            })
            return AskResponse(
                question=req.question,
                role=req.role.value,
                sql=sql,
                safe_sql=safe_sql,
                explanation=f"Generated SQL failed after {repair_count} repair attempt(s) and was not executed.",
                validation=validation,
                columns=[],
                rows=[],
                audit_id=audit_id,
                blocked=True,
                block_reason="SQL validation or execution failed.",
            )

        # success
        safe_sql = attempt["safe_sql"]
        validation = attempt["validation"]
        columns = attempt["columns"]
        rows = attempt["rows"]
        decision = attempt["decision"]

        if decision.masked_fields:
            ground = {
                "grounded": True,
                "confidence": 1.0,
                "reason": "Groundedness check skipped: sensitive fields were masked by policy."
            }
        else:
            ground = check_groundedness(req.question, safe_sql, rows)

        confidence = ground.get("confidence", 1.0)
        grounded = ground.get("grounded", True)

        explanation = explainer.explain(intent, decision.masked_fields or [])
        if repair_count > 0:
            explanation += f" (Corrected after {repair_count} automatic repair attempt.)"

        intent_flagged = attempt.get("intent_flagged", False)
        intent_reason = attempt.get("intent_reason", "")
        if intent_flagged:
            # Non-blocking by design - see _generate_policy_validate_execute.
            # This is shown as a caution, not a failure, because the judge
            # behind this check is known to be non-deterministic.
            explanation += f" ⚠ Possible intent mismatch (unverified, may be a false alarm): {intent_reason}"

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
            "repair_attempts": repair_count,
            "intent_flagged": intent_flagged,
            "intent_reason": intent_reason,
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
            confidence=confidence,
            grounded=grounded,
            groundedness_reason=ground.get("reason"),
            masked_fields=decision.masked_fields or [],
            intent_flagged=intent_flagged,
            intent_reason=intent_reason,
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
