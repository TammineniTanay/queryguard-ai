"""
Catches the "right syntax, wrong answer" class of hallucination that
sqlglot validation and successful execution both miss entirely. A query
can parse cleanly and run without error while still answering a different
question than the one asked - e.g. user asks for 2024 claims, LLM writes
WHERE strftime('%Y', claim_date) = '2023'. Nothing about that SQL is
syntactically wrong. It just isn't what was asked.

Approach: reverse-translate the generated SQL back into plain English,
then have a second LLM call compare that against the original question.
This is deliberately a different call than groundedness.py - groundedness
checks "do the RESULT ROWS support this answer", this checks "does the SQL
ITSELF match the question's filters/grouping/intent" before execution even
happens. They catch different failure modes and are not redundant with
each other.

Cost note: this adds one LLM call per request (two if you count the
reverse-translation as separate from the comparison, which it is below).
That's real latency and real cost - this is not free to run on every query
forever, it's a deliberate tradeoff for catching a hallucination class that
nothing else in the pipeline catches.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("FEATHERLESS_API_KEY"),
    base_url=os.getenv("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1")
)

MODEL = os.getenv("FEATHERLESS_MODEL", "Qwen/Qwen2.5-72B-Instruct")


@dataclass
class IntentCheckResult:
    is_valid: bool
    reason: str
    translated_intent: str


def _call_llm(system: str, user: str, temperature: float = 0.0) -> str:
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=300,
    )
    return response.choices[0].message.content.strip()


def validate_logical_intent(original_question: str, generated_sql: str) -> IntentCheckResult:
    """
    Reverse-translates SQL back to English, then checks whether that
    translation actually matches what was asked. Returns is_valid=False
    with a specific reason when they diverge, so the caller can feed that
    reason straight into the existing repair loop.
    """
    reverse_system = (
        "You are an expert data analyst. Read SQL and translate it into the "
        "exact business question it answers. Be specific about filters, date "
        "ranges, grouping, and any WHERE conditions. Do not describe syntax - "
        "describe what business question this query actually answers."
    )
    reverse_user = f"SQL:\n{generated_sql}\n\nWhat exact business question does this SQL answer?"

    translated_intent = _call_llm(reverse_system, reverse_user)

    judge_system = (
        "You are a reviewer checking for SEMANTIC hallucinations in generated SQL - "
        "not implementation style. Reply with exactly one line: either the word PASS, "
        "or FAIL followed by a colon and a specific reason.\n\n"
        "FAIL only for real mismatches: wrong date/year, wrong filter value, wrong "
        "aggregation (SUM vs AVG vs COUNT), wrong grouping column, a condition that "
        "contradicts the question, or a missing constraint the question explicitly "
        "required.\n\n"
        "PASS for implementation details that any correct SQL would need: joins "
        "required to reach a column, a LIMIT clause, column aliasing, using a "
        "table's actual column name instead of the user's casual phrasing, or "
        "ordering/formatting choices. These are not hallucinations even if the "
        "user didn't explicitly mention them."
    )
    judge_user = f"""Original request: {original_question}

What the SQL actually does: {translated_intent}

Does the SQL contain a real semantic mismatch (wrong filter, wrong date,
wrong aggregation, wrong grouping), as opposed to just necessary
implementation details?"""

    verdict = _call_llm(judge_system, judge_user)

    is_valid = verdict.strip().upper().startswith("PASS")
    reason = "" if is_valid else verdict.strip()

    return IntentCheckResult(is_valid=is_valid, reason=reason, translated_intent=translated_intent)
