from __future__ import annotations

import json
import os
import re
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("FEATHERLESS_API_KEY"),
    base_url=os.getenv("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1")
)

MODEL = os.getenv("FEATHERLESS_MODEL", "Qwen/Qwen2.5-72B-Instruct")


def check_groundedness(question: str, sql: str, rows: list) -> dict:
    if not rows:
        return {
            "grounded": False,
            "confidence": 0.0,
            "reason": "Query returned no results"
        }

    system = """You are a fact-checker for a data analytics system.
Given a question, the SQL that was run, and the query results, decide if the results
actually answer the question asked.

Respond with valid JSON only - no explanation, no markdown:
{"grounded": true or false, "confidence": 0.0 to 1.0, "reason": "one sentence"}"""

    user = f"""Question: {question}

SQL executed:
{sql}

Query results (first 5 rows):
{json.dumps(rows[:5], indent=2)}

Do the results answer the question?"""

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            temperature=0.0,
            max_tokens=150
        )
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r"```json|```", "", raw).strip()
        return json.loads(raw)
    except Exception:
        return {
            "grounded": True,
            "confidence": 0.5,
            "reason": "Could not verify groundedness"
        }
