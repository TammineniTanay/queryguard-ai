import asyncio
import yaml
import json
from app.langgraph_pipeline import run_pipeline

with open("eval/questions.yaml") as f:
    QUESTIONS = yaml.safe_load(f)

async def run_eval():
    results = []
    passed = 0

    for i, q in enumerate(QUESTIONS):
        print(f"\n[{i+1}/{len(QUESTIONS)}] {q['question']}")
        result = await run_pipeline(q["question"], role="analyst")

        sql = (result.get("sql") or "").upper()
        tables_used = result.get("tables_used", [])
        confidence = result.get("confidence", 0)

        # check expected tables
        tables_ok = all(t in tables_used for t in q.get("expected_tables", []))

        # check SQL contains expected keywords
        sql_ok = all(kw.upper() in sql for kw in q.get("expected_sql_contains", []))

        passed_this = tables_ok and sql_ok and result["status"] == "success"
        if passed_this:
            passed += 1

        results.append({
            "question": q["question"],
            "status": result["status"],
            "tables_ok": tables_ok,
            "sql_ok": sql_ok,
            "confidence": confidence,
            "passed": passed_this,
            "sql": result.get("sql")
        })

        status = "✅ PASS" if passed_this else "❌ FAIL"
        print(f"  {status} | confidence: {confidence} | tables: {tables_used}")

    accuracy = passed / len(QUESTIONS) * 100
    print(f"\n{'='*50}")
    print(f"ACCURACY: {passed}/{len(QUESTIONS)} = {accuracy:.1f}%")
    print(f"{'='*50}")

    with open("eval/results.json", "w") as f:
        json.dump({"accuracy": accuracy, "results": results}, f, indent=2)

    return accuracy

if __name__ == "__main__":
    asyncio.run(run_eval())
