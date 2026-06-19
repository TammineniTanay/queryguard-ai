from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class UserRole(str, Enum):
    executive = "executive"
    finance_analyst = "finance_analyst"
    clinical_analyst = "clinical_analyst"


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)
    user_id: str = Field(..., min_length=2, max_length=128)
    role: UserRole
    limit: int = Field(default=100, ge=1, le=500)


class ValidationResult(BaseModel):
    ok: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class AskResponse(BaseModel):
    question: str
    role: str
    sql: str
    safe_sql: str
    explanation: str
    validation: ValidationResult
    columns: List[str]
    rows: List[Dict[str, Any]]
    audit_id: str
    blocked: bool = False
    block_reason: Optional[str] = None
    # groundedness fields - surfaced separately from explanation so the
    # frontend can render a confidence badge instead of parsing prose
    confidence: Optional[float] = None
    grounded: Optional[bool] = None
    groundedness_reason: Optional[str] = None
    masked_fields: List[str] = Field(default_factory=list)
    # Non-blocking logical-intent warning. Deliberately separate from
    # `blocked`/`block_reason` - this check is known to be non-deterministic
    # (LLM-as-judge), so it is surfaced as an unverified caution, never as
    # a reason to withhold a result the rest of the pipeline confirmed works.
    intent_flagged: bool = False
    intent_reason: Optional[str] = None
