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
