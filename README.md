# Support-Ticket Triage Agent

An autonomous AI agent that reads incoming support tickets, decides what
information it needs, pulls that information itself using tools, and drafts or
escalates a response — with guardrails, cost tracking, and an eval suite.

This repo is being built in phases (see [`support-ticket-triage-agent-spec.md`](support-ticket-triage-agent-spec.md)).
**Phases 1–4 plus Phase 3b RAG and AgentMail email intake are implemented.**

---

## What works today (Phases 1–4 + 3b RAG + AgentMail)

- A **plain-Python agent loop** (no framework) where the LLM decides which tools
  to call, the loop runs them, feeds results back, and repeats until a final
  decision — capped by a safety step limit.
- **5 tools** behind a registry: `get_account_orders`, `search_knowledge_base`,
  `check_system_status`, `flag_for_escalation`, `log_resolution`.
- A **swappable LLM provider** abstraction:
  - `mock` — deterministic, **no API key needed**, keeps everything runnable and tests reproducible.
  - `gemini` — Google Gemini (free tier) via `google-genai` (with 429/503 retry).
- **Guardrails** (plain code, not prompts): billing/refund/cancellation always
  escalate; ticket-text money/lifecycle cues escalate even if the model
  mis-labels the category; low confidence drafts for review; only
  high-confidence FAQ / password_reset may auto-respond.
- **Eval suite**: 250 labeled tickets (`data/eval_tickets.jsonl`), scoring script
  (accuracy, per-category precision/recall, escalation safety rates), cached
  Gemini/mock runs under `evals/`. Latest Gemini Flash Lite full run:
  **95.2% category accuracy**, **90.4% action accuracy**, **0% high-risk
  auto-respond**.
- **Cost-aware model routing (Phase 4):** cheap vs strong Gemini models chosen
  by a heuristic router; tier + model name stored on each resolution.
- **Observability dashboard (Phase 4):** React UI for avg cost, escalation rate,
  routing mix, and recent tickets (`/dashboard/` or `dashboard` Vite app).
- **RAG knowledge retrieval (Phase 3b):** `search_knowledge_base` embeds the query
  with Gemini and retrieves top chunks from **Supabase pgvector**. When RAG is
  off or unavailable, it falls back to in-memory keyword search (offline-safe).
- **FastAPI** endpoints to submit tickets and read back the full decision trace.
- **AgentMail email intake:** inbound mail hits `POST /webhooks/agentmail`, runs
  the same triage path, and **auto-replies only** when guardrails choose
  `auto_respond` (billing/refund/cancel escalate — no auto-send).
- **SQLAlchemy** persistence (SQLite for tickets/logs by default; optional
  Postgres for tickets later) plus a separate `RAG_DATABASE_URL` for vectors.
- **Tests** covering tools, the reasoning loop, API, guardrails, routing, metrics, eval scoring, RAG fallback, and AgentMail webhook parsing.

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

### AgentMail email intake (optional)

Receive real emails into the agent (free AgentMail tier includes send + receive).

**One-time setup**

1. Get an API key at [agentmail.to](https://www.agentmail.to) and set in `.env`:
   ```env
   AGENTMAIL_API_KEY=am_...
   AGENTMAIL_INBOX_USERNAME=support-triage
   AGENTMAIL_AUTO_REPLY=true
   ```
2. Claim / note your **free static ngrok domain** in the
   [ngrok Domains dashboard](https://dashboard.ngrok.com/domains)
   (e.g. `your-name.ngrok-free.dev`).
3. Start the API, then start ngrok on that **same** domain every time:
   ```powershell
   uvicorn app.api.main:app --reload
   # other terminal — use YOUR static domain:
   ngrok http --url=https://your-name.ngrok-free.dev 8000
   ```
4. Register the webhook **once** (only when first setting up, or if the URL/secret changes):
   ```powershell
   python -m app.email.setup --webhook-url https://your-name.ngrok-free.dev/webhooks/agentmail
   ```
5. Paste printed `AGENTMAIL_INBOX_ID` and `AGENTMAIL_WEBHOOK_SECRET` into `.env`.

After that, daily restarts only need **API + ngrok** — you do **not** need to
re-register AgentMail as long as you keep using the same static domain.

**Demo:** email `support-triage@agentmail.to` — FAQ may auto-reply; billing/refund/cancel escalate.

Webhook endpoint: `POST /webhooks/agentmail`.

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

## Phase 3b — RAG (Supabase + pgvector)

Tickets and decision logs stay on local SQLite (`DATABASE_URL`). Knowledge-base
retrieval uses a **separate** Supabase Postgres URL with pgvector.

### Setup

1. Create a free project at [supabase.com](https://supabase.com).
2. In the SQL editor, run:
   ```sql
   create extension if not exists vector;
   ```
3. Project Settings → Database → copy the **Transaction pooler** URI (port `6543`).
4. Put it in `.env` (SQLAlchemy form — note the `postgresql+psycopg://` prefix):
   ```env
   ENABLE_RAG=true
   RAG_DATABASE_URL=postgresql+psycopg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres
   EMBEDDING_MODEL=gemini-embedding-001
   ```
5. Install deps (includes `psycopg`) and ingest seed docs:
   ```powershell
   pip install -r requirements.txt
   python -m app.rag.ingest
   ```

After ingest, `search_knowledge_base` returns `"source": "rag"` with similarity
scores. With `ENABLE_RAG=false` (default), it uses keyword matching instead.

> Optional later: move tickets/logs to Postgres by setting `DATABASE_URL` to a
> Supabase URL. That is independent of RAG.

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
  rag/
    embeddings.py # Gemini embeddings
    store.py      # pgvector upsert + similarity search
    retrieve.py   # rag_enabled / rag_search
    ingest.py     # seed docs into Supabase (`python -m app.rag.ingest`)
    seed_docs.py  # policy/FAQ corpus
  tools/
    tools.py     # tool implementations (RAG or keyword KB search)
    registry.py  # tool specs + safe dispatch
  db/
    database.py  # engine/session
    models.py    # Ticket, Resolution, DecisionLog
  api/
    main.py      # FastAPI endpoints + dashboard mount
    metrics.py   # rolled-up observability metrics
    schemas.py   # request/response models
  email/
    parse.py     # AgentMail webhook payload → IncomingEmail
    handler.py   # triage + safe auto-reply
    client.py    # AgentMail SDK helpers
    setup.py     # create inbox + register webhook (`python -m app.email.setup`)
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
foundation for the eval suite and observability dashboard.
