"""FastAPI app exposing the triage agent.

Endpoints:
  GET  /health                 -> liveness + which LLM provider is active
  POST /tickets                -> submit a ticket; runs the agent and returns the result
  GET  /tickets/{id}           -> fetch a ticket with its resolution and full decision log
  GET  /metrics/summary        -> rolled-up cost / escalation / routing stats (Phase 4)
  GET  /metrics/recent         -> latest tickets with cost + model tier (Phase 4)
  POST /webhooks/agentmail     -> AgentMail inbound email → triage (+ safe auto-reply)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.metrics import metrics_summary, recent_ticket_metrics
from app.api.schemas import (
    MetricsSummaryOut,
    RecentTicketMetricOut,
    TicketCreate,
    TicketDetailOut,
    TicketOut,
)
from app.config import settings
from app.db.database import SessionLocal, get_session, init_db
from app.db.models import Ticket
from app.service import triage_ticket

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Support-Ticket Triage Agent",
    version="0.3.0",
    description="An autonomous agent that reads support tickets, calls tools, "
    "and drafts or escalates a response — with guardrails, cost-aware routing, "
    "observability, and AgentMail email intake.",
)

# Dashboard (Vite) runs on another origin in dev; allow local frontends.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_DASHBOARD_DIST = Path(__file__).resolve().parents[2] / "dashboard" / "dist"


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, object]:
    from app.email.client import agentmail_configured
    from app.rag.retrieve import rag_enabled

    return {
        "status": "ok",
        "llm_provider": settings.llm_provider,
        "model_routing": settings.enable_model_routing,
        "gemini_model_cheap": settings.gemini_model_cheap,
        "gemini_model_strong": settings.gemini_model_strong,
        "rag_enabled": rag_enabled(),
        "embedding_model": settings.embedding_model,
        "agentmail_configured": agentmail_configured(),
        "agentmail_auto_reply": settings.agentmail_auto_reply,
        "agentmail_inbox_id": settings.agentmail_inbox_id or None,
    }


def _process_agentmail_payload(payload: dict[str, Any]) -> None:
    """Background worker: open a fresh DB session and run triage."""
    from app.email.handler import handle_agentmail_event

    session = SessionLocal()
    try:
        result = handle_agentmail_event(session, payload)
        logger.info("AgentMail webhook processed: %s", result)
    except Exception:  # noqa: BLE001
        logger.exception("AgentMail webhook processing failed")
        session.rollback()
    finally:
        session.close()


@app.post("/webhooks/agentmail")
async def agentmail_webhook(
    request: Request, background_tasks: BackgroundTasks
) -> dict[str, object]:
    """Receive AgentMail ``message.received`` events.

    Returns 200 quickly and triages in a background task. Auto-replies only
    when guardrails choose ``auto_respond`` (billing/refund/cancel escalate).
    """
    from app.email.client import verify_webhook_signature

    raw = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    try:
        payload = verify_webhook_signature(raw, headers)
    except Exception as exc:  # noqa: BLE001 — svix WebhookVerificationError
        logger.warning("AgentMail webhook verification failed: %s", exc)
        raise HTTPException(status_code=400, detail="invalid webhook signature") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid payload")

    background_tasks.add_task(_process_agentmail_payload, payload)
    return {"ok": True}


@app.post("/tickets", response_model=TicketDetailOut, status_code=201)
def create_ticket(payload: TicketCreate, session: Session = Depends(get_session)) -> Ticket:
    ticket = triage_ticket(
        session,
        subject=payload.subject,
        body=payload.body,
        customer_id=payload.customer_id,
        external_id=payload.external_id,
        channel=payload.channel,
    )
    return ticket


@app.get("/tickets/{ticket_id}", response_model=TicketDetailOut)
def get_ticket(ticket_id: int, session: Session = Depends(get_session)) -> Ticket:
    ticket = session.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="ticket not found")
    return ticket


@app.get("/tickets", response_model=list[TicketOut])
def list_tickets(session: Session = Depends(get_session)) -> list[Ticket]:
    return list(session.scalars(select(Ticket).order_by(Ticket.id.desc())))


@app.get("/metrics/summary", response_model=MetricsSummaryOut)
def get_metrics_summary(session: Session = Depends(get_session)) -> MetricsSummaryOut:
    return metrics_summary(session)


@app.get("/metrics/recent", response_model=list[RecentTicketMetricOut])
def get_metrics_recent(
    limit: int = 25, session: Session = Depends(get_session)
) -> list[RecentTicketMetricOut]:
    return recent_ticket_metrics(session, limit=min(max(limit, 1), 100))


# Serve the built dashboard if present (``cd dashboard && npm run build``).
if _DASHBOARD_DIST.is_dir():
    app.mount(
        "/dashboard",
        StaticFiles(directory=_DASHBOARD_DIST, html=True),
        name="dashboard",
    )
