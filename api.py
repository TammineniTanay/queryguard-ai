from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import sqlite3
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="QueryGuard AI", version="1.0.0")

DB_PATH = os.getenv("DATABASE_PATH", "data/sample.db")

class QueryRequest(BaseModel):
    question: str
    role: Optional[str] = "analyst"

class QueryResponse(BaseModel):
    status: str
    question: str
    sql: Optional[str] = None
    rows: Optional[list] = None
    tables_used: Optional[list] = None
    confidence: Optional[float] = None
    flagged: Optional[bool] = False
    message: Optional[str] = None

def execute_sql(sql: str) -> list:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(sql)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

@app.get("/health")
def health():
    return {"status": "ok", "service": "QueryGuard AI"}

@app.get("/schema")
def get_schema(role: str = "analyst"):
    from app.access_control import filter_schema_by_role
    return filter_schema_by_role(role)

@app.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    from app.langgraph_pipeline import run_pipeline
    result = await run_pipeline(request.question, request.role)
    return result

@app.post("/execute-sql")
def execute(sql: str, role: str = "analyst"):
    from app.access_control import check_sql_against_permissions
    allowed, msg = check_sql_against_permissions(sql, role)
    if not allowed:
        raise HTTPException(status_code=403, detail=msg)
    try:
        rows = execute_sql(sql)
        return {"status": "success", "rows": rows}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
