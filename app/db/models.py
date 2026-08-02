"""ORM models: tickets, their resolutions, and a full decision log.

The ``DecisionLog`` table is what makes the agent observable — every LLM turn
and every tool call is recorded with inputs/outputs, latency and cost, which
is the backbone for the eval suite and dashboard in later phases.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    subject: Mapped[str] = mapped_column(String(512))
    body: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(String(32), default="email")
    status: Mapped[str] = mapped_column(String(32), default="new")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    resolution: Mapped["Resolution | None"] = relationship(
        back_populates="ticket", uselist=False, cascade="all, delete-orphan"
    )
    decision_logs: Mapped[list["DecisionLog"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan", order_by="DecisionLog.step"
    )


class Resolution(Base):
    """The agent's final decision for a ticket."""

    __tablename__ = "resolutions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), unique=True)

    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    urgency: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # What the agent decided to do: auto_respond | draft_for_review | escalate_to_human
    action: Mapped[str | None] = mapped_column(String(32), nullable=True)
    draft_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Rolled-up run metrics.
    steps_taken: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)

    # Phase 4 — which model tier handled this ticket.
    model_tier: Mapped[str | None] = mapped_column(String(16), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    route_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    ticket: Mapped["Ticket"] = relationship(back_populates="resolution")


class DecisionLog(Base):
    """One row per agent step: an LLM turn or a tool call."""

    __tablename__ = "decision_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"))
    step: Mapped[int] = mapped_column(Integer)

    # "llm" | "tool" | "final"
    kind: Mapped[str] = mapped_column(String(16))
    tool_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tool_args: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tool_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)

    tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    ticket: Mapped["Ticket"] = relationship(back_populates="decision_logs")
