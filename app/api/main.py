"""FastAPI app exposing the triage agent.

Endpoints:
  GET  /health            -> liveness + which LLM provider is active
  POST /tickets           -> submit a ticket; runs the agent and returns the result
  GET  /tickets/{id}      -> fetch a ticket with its resolution and full decision log
  GET  /metrics/summary   -> rolled-up cost / escalation / routing stats (Phase 4)
  GET  /metrics/recent    -> latest tickets with cost + model tier (Phase 4)
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
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
from app.db.database import get_session, init_db
from app.db.models import Ticket
from app.service import triage_ticket

app = FastAPI(
    title="Support-Ticket Triage Agent",
    version="0.2.0",
    description="An autonomous agent that reads support tickets, calls tools, "
    "and drafts or escalates a response — with guardrails, cost-aware routing, "
    "and observability.",
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
    from app.rag.retrieve import rag_enabled

    return {
        "status": "ok",
        "llm_provider": settings.llm_provider,
        "model_routing": settings.enable_model_routing,
        "gemini_model_cheap": settings.gemini_model_cheap,
        "gemini_model_strong": settings.gemini_model_strong,
        "rag_enabled": rag_enabled(),
        "embedding_model": settings.embedding_model,
    }


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
