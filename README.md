# Support-Ticket Triage Agent

An autonomous AI agent that reads incoming support tickets, decides what
information it needs, pulls that information itself using tools, and drafts or
escalates a response — with guardrails, cost tracking, and an eval suite.

This repo is being built in phases (see [`support-ticket-triage-agent-spec.md`](support-ticket-triage-agent-spec.md)).
**Phases 1–4 (core agent, guardrails, eval suite, cost routing + dashboard) are implemented.**

---

## What works today (Phases 1–4)

- A **plain-Python agent loop** (no framework) where the LLM decides which tools
  to call, the loop runs them, feeds results back, and repeats until a final
  decision — capped by a safety step limit.
- **5 tools** behind a registry: `get_account_orders`, `search_knowledge_base`,
  `check_system_status`, `flag_for_escalation`, `log_resolution`.
- A **swappable LLM provider** abstraction:
  - `mock` — deterministic, **no API key needed**, keeps everything runnable and tests reproducible.
  - `gemini` — Google Gemini (free tier) via `google-genai` (with 429/503 retry).
- **Guardrails** (plain code, not prompts): billing/refund/cancellation always
  escalate; low confidence drafts for review; only high-confidence FAQ /
  password_reset may auto-respond.
- **Eval suite**: 250 labeled tickets (`data/eval_tickets.jsonl`), scoring script
  (accuracy, per-category precision/recall, escalation safety rates), cached
  Gemini/mock runs under `evals/`.
- **Cost-aware model routing (Phase 4):** cheap vs strong Gemini models chosen
  by a heuristic router; tier + model name stored on each resolution.
- **Observability dashboard (Phase 4):** React UI for avg cost, escalation rate,
  routing mix, and recent tickets (`/dashboard/` or `dashboard` Vite app).
- **FastAPI** endpoints to submit tickets and read back the full decision trace.
- **SQLAlchemy** persistence (SQLite now; one-line switch to Postgres/Supabase later)
  storing tickets, resolutions, and a per-step **decision log** (tools, tokens, cost, latency).
- **Tests** covering tools, the reasoning loop, API, guardrails, routing, metrics, and eval scoring.

> Real RAG (pgvector) and the optional multi-agent split are Phase 3b / Phase 5.

---

## Quick start

From the project root:

```bash
# 1. (recommended) create a virtual environment
python -m venv .venv
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate

# 2. install dependencies
pip install -r requirements.txt

# 3. (optional) configure — defaults already work with zero setup
copy .env.example .env      # Windows   (use `cp` on macOS/Linux)
```

### Run the demo (no API key required)

```bash
python -m app.cli
```

This runs the sample tickets in `data/sample_tickets.json` through the agent and
prints each step — tool calls, results, and the final decision.

Run a single custom ticket:

```bash
python -m app.cli --subject "Charged twice" --body "I was billed twice, customer_id: CUST-1001" --customer-id CUST-1001
```

### Run the API

```bash
uvicorn app.api.main:app --reload
```

Then open the interactive docs at http://127.0.0.1:8000/docs, or:

```bash
curl -X POST http://127.0.0.1:8000/tickets \
  -H "Content-Type: application/json" \
  -d '{"subject":"Charged twice","body":"billed twice, customer_id: CUST-1001","customer_id":"CUST-1001"}'
```

### Run the tests

```bash
pytest -q
```

### Run the eval suite (Phase 3)

```bash
# Build/refresh the labeled set (needs `datasets`; one-time / regenerable)
python -m evals.prepare_dataset

# Fast harness check (no API key)
python -m evals.run_eval --provider mock --limit 50

# Gemini baseline (uses .env; resumes from cache on re-run)
python -m evals.run_eval --provider gemini --limit 20
```

Reports land in `evals/results/`. Prefer `GEMINI_MODEL=gemini-flash-lite-latest`
for bulk evals — thinking models are much slower per ticket.

### Observability dashboard (Phase 4)

```bash
# terminal 1 — API
uvicorn app.api.main:app --reload

# terminal 2 — dashboard (dev, hot reload)
cd dashboard
npm install
npm run dev
```

Open http://127.0.0.1:5173 (proxies API calls to `:8000`).

Or build once and use the API-hosted UI:

```bash
cd dashboard && npm run build
uvicorn app.api.main:app --reload
# then open http://127.0.0.1:8000/dashboard/
```

Metrics endpoints: `GET /metrics/summary`, `GET /metrics/recent`.
---

## Using Gemini (optional)

1. Get a free API key at https://aistudio.google.com/apikey
2. In `.env` set:
   ```env
   LLM_PROVIDER=gemini
   GEMINI_API_KEY=your_key_here
   GEMINI_MODEL=gemini-flash-lite-latest
   ENABLE_MODEL_ROUTING=true
   GEMINI_MODEL_CHEAP=gemini-flash-lite-latest
   GEMINI_MODEL_STRONG=gemini-flash-latest
   ```
3. Re-run the CLI or API. Cost/token usage is recorded per step (estimates; free tier bills $0).
   With routing on, easy tickets use the cheap model and hard ones use the strong model.

> Prefer `gemini-flash-lite-latest` for evals / cheap tier. Some older flash models return 404 /
> zero free-tier quota on newly issued keys.

## Switching to Postgres / Supabase (later)

No code changes — just set `DATABASE_URL` in `.env` to your Supabase pooled
connection string and install the driver:

```bash
pip install "psycopg[binary]"
```
```env
DATABASE_URL=postgresql+psycopg://postgres.<ref>:<password>@<host>:6543/postgres
```
Enable pgvector once in the Supabase SQL editor for Phase 3 RAG:
```sql
create extension if not exists vector;
```

---

## Project layout

```
app/
  agent/
    llm.py       # provider abstraction: MockProvider, GeminiProvider
    loop.py      # the agent reasoning loop + decision parsing
    prompts.py   # system prompt + ticket formatting
    guardrails.py # Phase 2 action routing (escalate / draft / auto-respond)
    router.py    # Phase 4 cheap vs strong model routing
  tools/
    tools.py     # tool implementations (in-memory fixtures for now)
    registry.py  # tool specs + safe dispatch
  db/
    database.py  # engine/session
    models.py    # Ticket, Resolution, DecisionLog
  api/
    main.py      # FastAPI endpoints + dashboard mount
    metrics.py   # rolled-up observability metrics
    schemas.py   # request/response models
  service.py     # runs the agent and persists results
  config.py      # env-driven settings
  cli.py         # command-line demo runner
evals/           # Phase 3: prepare_dataset, run_eval, score
dashboard/       # Phase 4 React observability UI
data/
  sample_tickets.json
  eval_tickets.jsonl
tests/
```

---

## How the agent loop works

```
system + ticket ─▶ LLM ─▶ tool calls? ──yes──▶ run tools ─▶ feed results back ─┐
                    ▲                                                          │
                    └──────────────────────────────────────────────────────────┘
                          no │
                             ▼
                  parse final JSON decision
                  (category, urgency, confidence, draft, reasoning)
```

Every LLM turn and tool call is recorded in `decision_logs`, which is the
foundation for the eval suite and observability dashboard in later phases.
```
