import sqlite3
import os
from typing import TypedDict, Optional
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END

from app.llm_engine import ask_llm
from app.prompt_builder import build_table_picker_prompt, build_sql_prompt
from app.sql_guard import validate_sql, clean_sql
from app.groundedness import check_groundedness, rows_to_answer
from app.join_planner import get_join_path, format_joins_for_prompt, validate_tables_exist
from app.access_control import filter_schema_by_role, check_sql_against_permissions
from app.tavily_fallback import web_search

load_dotenv()

DB_PATH = os.getenv("DATABASE_PATH", "data/sample.db")


# ---  pipeline state ---

class State(TypedDict):
    question: str
    role: str
    schema: dict
    tables: list
    join_clauses: str
    sql: str
    rows: list
    answer: str
    groundedness: dict
    error: Optional[str]
    used_tavily: bool
    flagged: bool


# --- pipeline steps ---

def pick_tables(state: State) -> State:
    available = list(state["schema"].keys())
    system, user = build_table_picker_prompt(state["question"], available)
    raw = ask_llm(system, user)
    picked = [t.strip().lower() for t in raw.split(",")]
    state["tables"] = validate_tables_exist(picked) or available
    return state


def plan_joins(state: State) -> State:
    joins = get_join_path(state["tables"])
    state["join_clauses"] = format_joins_for_prompt(joins)
    return state


def generate_sql(state: State) -> State:
    relevant_schema = {t: state["schema"][t] for t in state["tables"] if t in state["schema"]}
    system, user = build_sql_prompt(state["question"], relevant_schema, state["join_clauses"])
    raw = ask_llm(system, user)
    state["sql"] = clean_sql(raw)
    return state


def check_sql(state: State) -> State:
    sql = state["sql"]

    if sql.upper() == "CANNOT_ANSWER":
        state["error"] = "CANNOT_ANSWER"
        return state

    valid, reason = validate_sql(sql, state["schema"])
    if not valid:
        state["error"] = reason
        return state

    allowed, msg = check_sql_against_permissions(sql, state["role"])
    if not allowed:
        state["error"] = msg
        state["flagged"] = True

    return state


def run_sql(state: State) -> State:
    if state.get("error"):
        return state
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(state["sql"])
        state["rows"] = [dict(r) for r in cur.fetchall()]
        conn.close()
    except Exception as e:
        state["error"] = f"SQL failed: {str(e)}"
    return state


def build_answer(state: State) -> State:
    if state.get("error"):
        return state
    state["answer"] = rows_to_answer(state["question"], state["rows"], state["sql"])
    return state


def verify_answer(state: State) -> State:
    if state.get("error"):
        return state
    result = check_groundedness(state["question"], state["sql"], state["rows"], state["answer"])
    state["groundedness"] = result
    if not result.get("grounded") or result.get("confidence", 1.0) < 0.6:
        state["flagged"] = True
    return state


def tavily_fallback(state: State) -> State:
    result = web_search(state["question"])
    if result["found"]:
        state["answer"] = result["answer"]
        state["used_tavily"] = True
        state["groundedness"] = {"grounded": True, "confidence": 0.7, "reason": "Answered via web search"}
    else:
        state["answer"] = "Could not find an answer from internal data or web search."
    return state


def route_after_check(state: State) -> str:
    error = state.get("error", "")
    if error == "CANNOT_ANSWER" or "SQL failed" in error:
        return "fallback"
    if error:
        return "stop"
    return "continue"


# --- build the graph ---

def build_pipeline():
    g = StateGraph(State)

    g.add_node("pick_tables", pick_tables)
    g.add_node("plan_joins", plan_joins)
    g.add_node("generate_sql", generate_sql)
    g.add_node("check_sql", check_sql)
    g.add_node("run_sql", run_sql)
    g.add_node("build_answer", build_answer)
    g.add_node("verify_answer", verify_answer)
    g.add_node("tavily_fallback", tavily_fallback)

    g.set_entry_point("pick_tables")
    g.add_edge("pick_tables", "plan_joins")
    g.add_edge("plan_joins", "generate_sql")
    g.add_edge("generate_sql", "check_sql")
    g.add_conditional_edges("check_sql", route_after_check, {
        "continue": "run_sql",
        "fallback": "tavily_fallback",
        "stop": END
    })
    g.add_edge("run_sql", "build_answer")
    g.add_edge("build_answer", "verify_answer")
    g.add_edge("verify_answer", END)
    g.add_edge("tavily_fallback", END)

    return g.compile()


PIPELINE = build_pipeline()


async def run_pipeline(question: str, role: str = "analyst") -> dict:
    schema = filter_schema_by_role(role)

    result = await PIPELINE.ainvoke({
        "question": question,
        "role": role,
        "schema": schema,
        "tables": [],
        "join_clauses": "",
        "sql": "",
        "rows": [],
        "answer": "",
        "groundedness": {},
        "error": None,
        "used_tavily": False,
        "flagged": False
    })

    if result.get("error") and not result.get("answer"):
        return {
            "status": "error",
            "question": question,
            "message": result["error"],
            "flagged": result.get("flagged", False)
        }

    return {
        "status": "success",
        "question": question,
        "sql": result.get("sql"),
        "rows": result.get("rows", []),
        "tables_used": result.get("tables", []),
        "answer": result.get("answer"),
        "confidence": result.get("groundedness", {}).get("confidence"),
        "flagged": result.get("flagged", False),
        "used_tavily": result.get("used_tavily", False),
        "message": result.get("groundedness", {}).get("reason")
    }
