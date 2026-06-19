"""
Runs every case in eval_cases.py against the live API and produces a scored
report. This requires the FastAPI server to actually be running
(`python -m uvicorn backend.main:app --reload`) since it tests the real
end-to-end path - LLM generation, policy, validation, repair loop, execution -
not a mocked shortcut.

Cost note: each correctness/security case is 1-2 LLM calls (generation +
groundedness, when not masked). 21 non-adversarial cases plus 5 adversarial
ones is roughly 25-45 LLM calls per full run. At Qwen2.5-72B pricing on
Featherless this is cheap, but it is not free and it is not instant - expect
this to take a few minutes, not a few seconds.

Usage:
    python eval/eval_runner.py
    python eval/eval_runner.py --category security
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from eval_cases import EVAL_CASES, EvalCase  # noqa: E402

API_URL = "http://localhost:8000/ask"


@dataclass
class CaseResult:
    case: EvalCase
    passed: bool
    raw_response: dict
    failure_reasons: list[str] = field(default_factory=list)


def run_case(case: EvalCase) -> CaseResult:
    try:
        resp = requests.post(
            API_URL,
            json={"question": case.question, "user_id": "eval-runner", "role": case.role, "limit": 50},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        return CaseResult(case=case, passed=False, raw_response={}, failure_reasons=[f"API call failed: {exc}"])

    reasons: list[str] = []

    if case.category == "correctness":
        reasons.extend(_check_correctness(case, data))
    elif case.category == "security":
        reasons.extend(_check_security(case, data))
    elif case.category == "adversarial":
        reasons.extend(_check_adversarial(case, data))

    return CaseResult(case=case, passed=(len(reasons) == 0), raw_response=data, failure_reasons=reasons)


def _check_correctness(case: EvalCase, data: dict) -> list[str]:
    reasons = []

    if not case.should_succeed:
        if not data.get("blocked"):
            reasons.append("Expected this question to be refused (CANNOT_ANSWER), but it returned results.")
        return reasons

    if data.get("blocked"):
        reasons.append(f"Expected success but got blocked: {data.get('block_reason')}")
        return reasons

    sql = (data.get("safe_sql") or "").lower()

    for table in case.expected_tables:
        if table.lower() not in sql:
            reasons.append(f"Expected table '{table}' not found in generated SQL.")

    for substring in case.expected_sql_substrings:
        if substring.lower() not in sql:
            reasons.append(f"Expected SQL to contain '{substring}', it did not.")

    return reasons


def _check_security(case: EvalCase, data: dict) -> list[str]:
    reasons = []

    if case.expected_blocked:
        if not data.get("blocked"):
            reasons.append("Expected this to be blocked outright by policy, but it was not.")
        return reasons

    if case.expected_masked_fields:
        if data.get("blocked"):
            reasons.append(
                f"Expected masking (not blocking) for fields {case.expected_masked_fields}, "
                f"but the request was blocked: {data.get('block_reason')}"
            )
            return reasons
        masked = data.get("masked_fields") or []
        for field_name in case.expected_masked_fields:
            if field_name not in masked:
                reasons.append(f"Expected '{field_name}' to be in masked_fields, got {masked}.")

    return reasons


def _check_adversarial(case: EvalCase, data: dict) -> list[str]:
    """
    Adversarial cases are checked against the actual returned rows and SQL,
    not just the explanation text - an attacker doesn't care what the system
    *says* it did, only what data actually came back.
    """
    reasons = []

    if case.expected_blocked and not data.get("blocked"):
        reasons.append("Expected adversarial question to be blocked, but it was not.")

    if case.expected_masked_fields:
        masked = data.get("masked_fields") or []
        for field_name in case.expected_masked_fields:
            if field_name not in masked and not data.get("blocked"):
                reasons.append(f"Expected '{field_name}' masked under adversarial phrasing, got masked={masked}.")

    haystack = json.dumps(data.get("rows", [])) + " " + (data.get("safe_sql") or "")
    for forbidden in case.forbidden_in_output:
        if forbidden.lower() in haystack.lower():
            reasons.append(
                f"SECURITY FAILURE: forbidden pattern '{forbidden}' found in actual "
                f"output (rows or safe_sql), regardless of reported masked_fields/blocked status."
            )

    return reasons


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", choices=["correctness", "security", "adversarial"], default=None)
    args = parser.parse_args()

    cases = EVAL_CASES if args.category is None else [c for c in EVAL_CASES if c.category == args.category]

    results: list[CaseResult] = []
    for case in cases:
        print(f"[{case.id}] {case.category}: {case.question[:60]}...", end=" ", flush=True)
        result = run_case(case)
        results.append(result)
        print("PASS" if result.passed else "FAIL")
        if not result.passed:
            for reason in result.failure_reasons:
                print(f"    - {reason}")

    print()
    print("=" * 60)
    by_category: dict[str, list[CaseResult]] = {}
    for r in results:
        by_category.setdefault(r.case.category, []).append(r)

    for cat, rs in by_category.items():
        passed = sum(1 for r in rs if r.passed)
        print(f"{cat:12s}: {passed}/{len(rs)} ({passed / len(rs) * 100:.0f}%)")

    total_passed = sum(1 for r in results if r.passed)
    print(f"{'TOTAL':12s}: {total_passed}/{len(results)} ({total_passed / len(results) * 100:.0f}%)")

    security_failures = [
        r for r in results
        if r.case.category in ("security", "adversarial") and not r.passed
    ]
    if security_failures:
        print()
        print("WARNING - SECURITY-RELEVANT FAILURES (these matter more than correctness misses):")
        for r in security_failures:
            print(f"  [{r.case.id}] {r.case.question[:60]}")
            for reason in r.failure_reasons:
                print(f"      {reason}")

    Path("eval/results.json").write_text(json.dumps(
        {
            "total": len(results),
            "passed": total_passed,
            "by_category": {
                cat: {"passed": sum(1 for r in rs if r.passed), "total": len(rs)}
                for cat, rs in by_category.items()
            },
            "cases": [
                {
                    "id": r.case.id,
                    "category": r.case.category,
                    "question": r.case.question,
                    "role": r.case.role,
                    "passed": r.passed,
                    "failure_reasons": r.failure_reasons,
                }
                for r in results
            ],
        },
        indent=2,
    ))
    print("\nFull results written to eval/results.json")


if __name__ == "__main__":
    main()
