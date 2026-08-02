# Support-Ticket Triage Agent — Full Project Spec

## What This Is

An autonomous AI agent that reads incoming support tickets, decides what information it needs, pulls that information itself using tools, and drafts or escalates a response — with guardrails, cost tracking, and an eval suite proving it actually works.

This is **not**:
- An ML project (no training/fine-tuning — you call an existing LLM)
- A raw API wrapper (the value is in orchestration, guardrails, evals, and cost control built around the model, not the API call itself)

It **is** an agentic system with backend engineering as its foundation — the exact combination "AI Agent Engineer" roles screen for in 2026.

---

## Architecture

### 1. Agent Core (the actual "agent" part)
A single LLM (Claude) with access to tools, reasoning in a loop — it decides which tools to call, in what order, and when it has enough information to respond. Not a scripted sequence.

**Tools available to the agent (via MCP):**
- `get_account_orders(customer_id)` — order/billing history
- `search_knowledge_base(query)` — policy docs, FAQs (RAG-backed)
- `check_system_status()` — for technical tickets
- `flag_for_escalation(reason)` — hands off to human
- `log_resolution(ticket_id, outcome)` — records what happened

**Example flow:**
```
Ticket: "Charged twice for my subscription"
Agent reasons: "billing issue → need order history"
  → calls get_account_orders
Agent reasons: "sees duplicate charge → need refund policy"
  → calls search_knowledge_base("duplicate charge refund policy")
Agent reasons: "policy allows auto-refund within 24h, charges are 2h apart"
  → drafts response, OR flags for escalation (see guardrails below)
```

### 2. Guardrail Layer (wraps the agent, doesn't replace it)
Hard rules in plain code — not prompts — that constrain what the agent is allowed to do autonomously:
```python
def check_guardrails(agent_decision, category, confidence):
    if category in ["billing", "refund", "cancellation"]:
        return "escalate_to_human"          # never auto-send, regardless of confidence
    if confidence < 0.75:
        return "draft_for_review"           # low trust = human checks first
    if category in ["password_reset", "faq"] and confidence >= 0.9:
        return "auto_respond"               # safe, low-risk, automate
    return "draft_for_review"               # default to caution
```
This is your answer to the OWASP "LLM06 Excessive Agency" interview question — least-privilege tool scope + explicit human checkpoints for irreversible actions.

### 3. Eval Suite
- Hand-label 200–300 tickets from your dataset: correct category, correct urgency, "was the response acceptable" (yes/no)
- Score the agent against this labeled set after every prompt/logic change
- Track accuracy, precision per category, and false-escalation rate over time
- This is reportedly the single most-checked skill in 2026 AI hiring — walk-through-your-eval is asked at every level

### 4. Cost Optimization
- Route simple tickets (FAQ, password reset) to a cheaper/faster model
- Route complex or ambiguous tickets to a stronger model
- Log $ and tokens per ticket
- Be able to say: "average cost per ticket is $X, here's the tradeoff I made between cost and accuracy"

### 5. Observability
- Log every agent decision: which tools it called, why, confidence, final action, cost, latency
- Simple dashboard: accuracy over time, cost per ticket, escalation rate, failure examples
- This is what lets you answer "how do you know it's still working after you changed the prompt"

### 6. Optional v2: Multi-Agent (Supervisor + Specialists)
Once single-agent works, split into:
- **Supervisor** — reads ticket, delegates to the right specialist
- **Billing specialist** — only has billing tools
- **Technical specialist** — only has technical tools
- **Account specialist** — only has account tools

Value: tool isolation (billing agent literally cannot call technical tools), failure containment (one specialist timing out doesn't break others). Only add this if you can explain *why* — "when would you NOT use multi-agent" is a real interview question, and over-engineering without justification is a flag, not a strength.

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Agent/LLM | Claude API (Anthropic) | reasoning, tool-calling |
| Orchestration | LangGraph or raw Python state loop | manages the agent's reasoning loop |
| Tool layer | MCP | standardized tool interface (you've already built this once) |
| Backend | FastAPI | API layer, service logic |
| Database | PostgreSQL | tickets, eval labels, logs |
| Vector store | pgvector | knowledge base retrieval (RAG) |
| Async | Redis | task queue if processing tickets async |
| Eval scoring | Custom script (+ optionally RAGAS) | accuracy tracking |
| Dashboard | React | visualize accuracy/cost/escalation |
| Deployment | Docker + AWS | containerized, cheap hosting for a portfolio project |

---

## Data Source
Public support-ticket datasets (Kaggle, HuggingFace, or Zendesk sample sets) — no need for real customer data. Aim for a few hundred to a couple thousand tickets so evals have something meaningful to run against.

---

## Build Plan (Phased)

**Phase 1 — Core agent (get it working)**
- Set up FastAPI + Postgres schema (tickets, logs)
- Build the agent loop with 2-3 tools via MCP
- Manual testing on a handful of tickets

**Phase 2 — Guardrails**
- Add rule-based routing layer around agent decisions
- Test that billing/refund never auto-sends

**Phase 3 — Eval suite**
- Label 200-300 tickets
- Build scoring script, run baseline accuracy
- Iterate on prompts, re-score, track improvement

**Phase 4 — Cost + observability**
- Add model routing (cheap vs. strong model by complexity)
- Structured logging of every decision
- Build the dashboard

**Phase 5 (optional) — Multi-agent v2**
- Split into supervisor + specialists once single-agent is solid

---

## Skills This Demonstrates
Agent orchestration · MCP integration · eval design · prompt engineering · RAG · cost optimization · safety/guardrails (OWASP LLM06) · production observability · FastAPI/Postgres/Redis/Docker backend · (optional) multi-agent architecture

---

## Outcome / Deliverables
- Working repo with README, architecture diagram, demo video/GIF
- Live or easily-runnable demo (even just local Docker Compose)
- Eval results you can quote (e.g. "92% classification accuracy on 250 labeled tickets")
- Cost numbers you can quote (e.g. "$0.03 avg cost per ticket with 70/30 cheap/strong model split")

**Resume bullet:**
"Built an agentic support-ticket triage system using Claude + MCP tool orchestration; designed eval suite (250+ labeled tickets, 92% classification accuracy) and cost-aware model routing, reducing avg cost per ticket by X% while maintaining accuracy."

**Interview story you can now tell:**
- Why you chose single-agent vs. multi-agent (and when you'd switch)
- What confidence threshold you set for auto-response and why
- What your eval caught that you didn't expect
- How you controlled cost without sacrificing accuracy

This gives you a project where you're not just repeating "I used LangChain" — you can walk through the actual engineering tradeoffs, which is exactly what's being screened for.
