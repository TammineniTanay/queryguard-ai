import json
from app.llm_engine import ask_llm


def check_groundedness(question, sql, rows, answer):
    """
    Checks whether the answer is actually supported by the query results.
    Returns a dict with grounded (bool), confidence (0-1), and reason.
    """
    if not rows:
        return {"grounded": False, "confidence": 0.0, "reason": "Query returned no data"}

    system = """You are a fact-checker. Given a SQL result and a natural language answer,
decide if the answer is supported by the data.

Respond with valid JSON only:
{"grounded": true or false, "confidence": 0.0 to 1.0, "reason": "short explanation"}"""

    user = f"""Question: {question}

SQL used: {sql}

Query result (first 5 rows): {json.dumps(rows[:5], indent=2)}

Answer to check: {answer}

Is this answer grounded in the query result?"""

    raw = ask_llm(system, user)

    try:
        raw = re.sub(r"```json|```", "", raw).strip() if "```" in raw else raw
        return json.loads(raw)
    except Exception:
        return {"grounded": False, "confidence": 0.0, "reason": "Could not parse check result"}


def rows_to_answer(question, rows, sql):
    """Turns raw SQL rows into a plain English answer."""
    if not rows:
        return "No results found."

    system = (
        "You are a data analyst. Convert the SQL results into a clear, "
        "concise answer. Only use what is in the results, nothing else."
    )
    user = f"Question: {question}\nSQL: {sql}\nResults: {json.dumps(rows[:10])}\nAnswer:"
    return ask_llm(system, user, temperature=0.1)


import re
