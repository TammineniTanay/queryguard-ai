from __future__ import annotations

from backend.core.catalog import Catalog
from backend.core.nl_router import NlRouter
from backend.core.sql_generator import SqlGenerator
from backend.core.sql_validator import SqlValidator
from backend.security.policy import PolicyEngine


def test_blocks_write_intent() -> None:
    intent = NlRouter().route("drop the claims table")
    assert intent.blocked_reason is not None


def test_generates_joined_sql_for_department_metric() -> None:
    catalog = Catalog("data/catalog.yml")
    intent = NlRouter().route("total claim amount by department")
    sql = SqlGenerator(catalog).generate(intent)
    assert "JOIN departments" in sql
    assert "SUM(c.claim_amount)" in sql


def test_executive_cannot_access_phi_diagnosis() -> None:
    catalog = Catalog("data/catalog.yml")
    intent = NlRouter().route("average claim amount by diagnosis")
    sql = SqlGenerator(catalog).generate(intent)
    decision = PolicyEngine(catalog).apply(sql, "executive")
    assert decision.allowed is False
    assert "diagnosis" in decision.reason


def test_finance_masks_email_detail() -> None:
    catalog = Catalog("data/catalog.yml")
    intent = NlRouter().route("list patient emails and claim amounts")
    sql = SqlGenerator(catalog).generate(intent)
    decision = PolicyEngine(catalog).apply(sql, "finance_analyst")
    assert decision.allowed is True
    assert "***MASKED***" in decision.sql


def test_validator_blocks_select_star() -> None:
    catalog = Catalog("data/catalog.yml")
    result = SqlValidator(catalog).validate("SELECT * FROM claims LIMIT 10")
    assert not result.ok
