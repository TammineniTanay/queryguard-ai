# QueryGuard AI

Secure natural-language analytics over a governed, BigQuery-style schema. Ask a business question in plain English, get back SQL, results, and a visible record of what got masked and how confident the system is in its own answer.

Built in ~32 hours during Buildathon Dallas 2026 (event cut short by an infrastructure incident — see [Background](#background)), then extended afterward to close gaps that a real hackathon timeline doesn't allow for.

## Why this exists

Most "chat with your data" demos stop at NL → SQL. Two things break that in production:

1. **The LLM doesn't know who's asking.** Without a permissions layer, it will happily write SQL that selects a patient's email or diagnosis code for someone who shouldn't see either.
2. **A working query isn't the same as a correct answer.** SQL can execute cleanly and still not actually answer the question that was asked.

QueryGuard AI treats both as first-class problems instead of afterthoughts.

## Architecture

```
Natural language question
        │
        ▼
  NlRouter            — blocks destructive intent (delete/drop/update) before the LLM ever sees it
        │
        ▼
  SqlGenerator         — LLM (Featherless AI / Qwen2.5-72B) writes SQL against the full schema.
        │                 Deliberately schema-blind to permissions — see "Why the LLM is allowed
        │                 to see PII" below.
        ▼
  PolicyEngine         — role-based: denies disallowed tables outright, masks sensitive
        │                 columns in place, applies row-level filters
        ▼
  SqlValidator          — parses with sqlglot (not regex): blocks SELECT *, destructive
        │                 statements, unknown tables/columns
        ▼
  ┌─────────────────┐
  │  Repair loop     │  if validation or execution fails, the exact error is fed back
  │  (max 1 retry)   │  to the LLM for one corrected attempt before giving up
  └─────────────────┘
        │
        ▼
  SQLite execution     — real query against a seeded demo database
        │
        ▼
  Groundedness check    — a second LLM call asks "do these results actually answer the
        │                 question?" and returns a confidence score. Skipped (not run)
        │                 when the policy layer already masked fields, since a masked
        │                 value is supposed to look wrong to a fact-checker — that's
        │                 the policy working, not a hallucination.
        ▼
  Audit log + response — every question, decision, and confidence score is logged with
                          a UUID. The frontend shows generated SQL, post-policy SQL,
                          confidence, and which fields were masked, side by side.
```

### Why the LLM is allowed to see PII

An earlier version of the prompt told the LLM "never use sensitive columns." The result: asked for a patient's email, the model refused outright with `CANNOT_ANSWER` — even for roles that were supposed to get a masked-but-present answer. The model was doing the policy engine's job badly instead of doing its own job well.

The fix was to separate concerns properly: the LLM's only responsibility is translating English into correct SQL against the *full* schema. The `PolicyEngine` — a deterministic, auditable, non-LLM component — decides afterward whether each field gets returned, masked, or blocks the query entirely. This is also just more honest about where the security boundary actually lives: in code you can read and test, not in a prompt you hope the model obeys.

## Access control model

Three roles, defined in [`data/catalog.yml`](data/catalog.yml):

| Role | Denied entirely | Masked | Row filters |
|---|---|---|---|
| `executive` | PHI, PII | — | none |
| `finance_analyst` | PHI | PII | none |
| `clinical_analyst` | — | PII | restricted to 4 named regions |

Try the same question as different roles to see the difference:

> *List patient emails and claim amounts*

- as `finance_analyst` → returns claim amounts, email column shown as `***MASKED***`
- as `executive` → blocked outright (PHI/PII denied, not just masked)

## What's actually verified working

This list is deliberately narrow — only things tested end-to-end, not aspirational:

- Multi-table NL → SQL with real joins (`claims` + `departments`, `claims` + `patients`)
- Role-based masking confirmed via UI screenshot, not just code review
- Confidence scoring confirmed to read 100%/grounded when masking occurs, instead of incorrectly penalizing correct redaction
- SQL repair loop wired and exercised (validation errors get fed back with one retry budget); not yet forced to trigger in manual testing since the underlying model rarely needs it for this schema's complexity
- Audit logging with UUID per request
- **18-case automated eval suite** ([`eval/eval_cases.py`](eval/eval_cases.py), run via [`eval/eval_runner_v2.py`](eval/eval_runner_v2.py)), hitting the live API end-to-end and scoring against explicit expected tables/SQL substrings/masked-fields — not just running and eyeballing the output. Three categories: 9 correctness cases (including 2 that should correctly refuse), 4 security cases (deny vs. mask), 5 adversarial cases (prompt injection, role-claim spoofing in the question text, SQL-injection-flavored input, compound questions smuggling a sensitive request alongside a legitimate one). **Result: 18/18 passing.** This is a small, hand-built eval set, not a large randomized benchmark — the honest claim is "passes this specific adversarial suite," not "provably secure."

## What's explicitly not done

- No multi-hop join planning beyond the two joins the demo schema defines
- The eval suite is 18 hand-written cases, not a large or randomly sampled benchmark — good first signal, not a statistically rigorous accuracy claim
- `BigQueryAdapter` exists as a stub for swapping warehouses but is untested — SQLite is the only adapter actually exercised
- Tavily web-search fallback is wired but not part of the core demo path
- No rate limiting or auth on the API beyond the role parameter itself — fine for a local demo, not production-ready as-is

## Stack

- **LLM**: Featherless AI, `Qwen/Qwen2.5-72B-Instruct` (OpenAI-compatible API)
- **Backend**: FastAPI
- **SQL parsing/validation**: sqlglot
- **Database**: SQLite (BigQuery-shaped schema, swappable adapter)
- **Frontend**: Streamlit

## Running it locally

```bash
git clone https://github.com/TammineniTanay/queryguard-ai
cd queryguard-ai
pip install -r requirements.txt
```

Create `.env`:
```env
FEATHERLESS_API_KEY=your-key-here
FEATHERLESS_BASE_URL=https://api.featherless.ai/v1
FEATHERLESS_MODEL=Qwen/Qwen2.5-72B-Instruct
TAVILY_API_KEY=your-key-here
```

Seed the database (already included as `data/demo.db`, regenerate if needed):
```bash
python scripts/seed_demo_db.py
```

Run the API:
```bash
python -m uvicorn backend.main:app --reload
```

Run the UI (separate terminal):
```bash
streamlit run frontend/app.py
```

Open `localhost:8501`, pick a role, ask a question.

### Running the eval suite

With the API running (above), in a separate terminal:

```bash
python eval/eval_runner_v2.py
```

This sends 18 labeled questions through the real pipeline — not a mocked shortcut — and checks actual returned SQL, masked fields, and row contents against explicit expectations. Takes a few minutes since each case is a real LLM call. Run a single category with `--category security` or `--category adversarial`.

## Background

Built at Buildathon Dallas 2026. The event was cut short partway through due to a wifi infrastructure failure and a safety incident with the organizing team, which the organizers later confirmed via email and said they had filed a police report over. Development continued independently after the event ended, since the architecture and code were already real and worth finishing properly.

## Team

- **Tanay Tammineni** — LLM pipeline, prompt design, groundedness/confidence scoring, SQL repair loop, integration
- **Teammate** — catalog/schema design, policy engine, SQL validator, SQLite adapter, audit logging, frontend
