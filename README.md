# QueryGuard AI

> Natural language to SQL engine with hallucination prevention and PHI/PII access control.

Built at **Buildathon Dallas 2026** in 32 hours.

## What it does

- Ask questions in plain English → get SQL + answers from real data
- **Hallucination prevention**: CRAG-style groundedness check flags low-confidence answers
- **PHI/PII blocking**: sensitive columns blocked at planning stage before SQL generates
- **Multi-table reasoning**: semantic join planner uses only approved join paths
- **Web fallback**: Tavily search when internal data can't answer
- **Role-based access**: analyst vs admin roles with different column visibility

## Architecture

```
User Question
     ↓
Table Selector (LLM picks relevant tables)
     ↓
Join Planner (approved join paths only)
     ↓
SQL Generator (Featherless AI / Llama 3.3 70B)
     ↓
SQL Guardrails (block SELECT *, DROP, PHI columns)
     ↓
SQL Execution (SQLite)
     ↓
Answer Generator
     ↓
Groundedness Check (CRAG-style confidence score)
     ↓
Flagged if confidence < 60% → Tavily fallback
```

## Stack

- **LLM**: Featherless AI (Llama 3.3 70B, OpenAI-compatible)
- **Pipeline**: LangGraph
- **Backend**: FastAPI
- **Frontend**: Streamlit
- **Database**: SQLite
- **Search fallback**: Tavily
- **Data**: E-commerce (orders, customers, products, reviews)

## Setup

```bash
git clone https://github.com/TammineniTanay/queryguard-ai
cd queryguard-ai
pip install -r requirements.txt
cp .env.example .env
# Add your API keys to .env

# Load dataset
python data/load_dataset.py

# Start API
uvicorn app.api:app --reload

# Start UI (new terminal)
streamlit run frontend/streamlit_app.py
```

## Eval

```bash
python eval/eval_runner.py
```

## Team

- **Tanay Tammineni** — AI pipeline, LangGraph, hallucination prevention, SQL guardrails
- **[Teammate]** — Data layer, schema ingestion, FastAPI, access control
