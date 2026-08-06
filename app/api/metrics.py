"""Observability metrics derived from persisted triage runs."""

from __future__ import annotations

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.agent.guardrails import AUTO_RESPOND, DRAFT_FOR_REVIEW, ESCALATE_TO_HUMAN
from app.api.schemas import MetricsSummaryOut, RecentTicketMetricOut
from app.db.models import Resolution, Ticket


def metrics_summary(session: Session) -> MetricsSummaryOut:
    resolutions = list(session.scalars(select(Resolution)))
    n = len(resolutions)
    if n == 0:
        return MetricsSummaryOut(
            ticket_count=0,
            avg_cost_usd=0.0,
            total_cost_usd=0.0,
            avg_latency_ms=0.0,
            escalation_rate=0.0,
            auto_respond_rate=0.0,
            draft_rate=0.0,
            cheap_tier_share=0.0,
            strong_tier_share=0.0,
            by_category={},
            by_action={},
            by_tier={},
        )

    total_cost = sum(r.cost_usd or 0.0 for r in resolutions)
    total_lat = sum(r.latency_ms or 0 for r in resolutions)
    actions = Counter(r.action or "unknown" for r in resolutions)
    categories = Counter(r.category or "unknown" for r in resolutions)
    tiers = Counter(r.model_tier or "unrouted" for r in resolutions)

    def rate(action: str) -> float:
        return actions.get(action, 0) / n

    routed = sum(tiers.get(t, 0) for t in ("cheap", "strong"))
    cheap_share = (tiers.get("cheap", 0) / routed) if routed else 0.0
    strong_share = (tiers.get("strong", 0) / routed) if routed else 0.0

    return MetricsSummaryOut(
        ticket_count=n,
        avg_cost_usd=round(total_cost / n, 6),
        total_cost_usd=round(total_cost, 6),
        avg_latency_ms=round(total_lat / n, 1),
        escalation_rate=round(rate(ESCALATE_TO_HUMAN), 4),
        auto_respond_rate=round(rate(AUTO_RESPOND), 4),
        draft_rate=round(rate(DRAFT_FOR_REVIEW), 4),
        cheap_tier_share=round(cheap_share, 4),
        strong_tier_share=round(strong_share, 4),
        by_category=dict(categories),
        by_action=dict(actions),
        by_tier=dict(tiers),
    )


def recent_ticket_metrics(session: Session, limit: int = 25) -> list[RecentTicketMetricOut]:
    tickets = list(
        session.scalars(
            select(Ticket)
            .options(joinedload(Ticket.resolution))
            .order_by(Ticket.id.desc())
            .limit(limit)
        )
    )
    out: list[RecentTicketMetricOut] = []
    for t in tickets:
        r = t.resolution
        out.append(
            RecentTicketMetricOut(
                id=t.id,
                subject=t.subject,
                category=r.category if r else None,
                action=r.action if r else None,
                confidence=r.confidence if r else None,
                cost_usd=r.cost_usd if r else 0.0,
                latency_ms=r.latency_ms if r else 0,
                model_tier=r.model_tier if r else None,
                model_name=r.model_name if r else None,
                created_at=t.created_at,
            )
        )
    return out
