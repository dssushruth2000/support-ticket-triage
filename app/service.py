"""Service layer: orchestrates a full triage run and persists the results.

This is the seam between the pure agent loop and the database. The API and CLI
both go through here so behavior stays consistent.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.agent.guardrails import check_guardrails
from app.agent.llm import LLMProvider, get_provider, resolve_model_for_tier
from app.agent.loop import run_agent
from app.agent.router import RouteDecision, route_ticket
from app.config import settings
from app.db.models import DecisionLog, Resolution, Ticket
from app.tools import ToolRegistry, build_default_registry


def _select_provider(
    subject: str,
    body: str,
    provider: LLMProvider | None,
) -> tuple[LLMProvider, RouteDecision | None, str | None]:
    """Apply model routing unless a provider was explicitly injected (tests)."""
    if provider is not None:
        return provider, None, getattr(provider, "_model", provider.name)

    if not settings.enable_model_routing:
        p = get_provider()
        model_name = getattr(p, "_model", settings.llm_provider)
        return p, None, model_name

    decision = route_ticket(subject, body)
    model_name = resolve_model_for_tier(decision.tier)
    # Mock ignores the concrete model name but still records the tier.
    if settings.llm_provider.lower().strip() == "gemini":
        p = get_provider(model=model_name)
    else:
        p = get_provider()
    return p, decision, model_name


def triage_ticket(
    session: Session,
    *,
    subject: str,
    body: str,
    customer_id: str | None = None,
    external_id: str | None = None,
    channel: str = "email",
    provider: LLMProvider | None = None,
    registry: ToolRegistry | None = None,
) -> Ticket:
    provider, route, model_name = _select_provider(subject, body, provider)
    registry = registry or build_default_registry()

    ticket = Ticket(
        subject=subject,
        body=body,
        customer_id=customer_id,
        external_id=external_id,
        channel=channel,
        status="processing",
    )
    session.add(ticket)
    session.flush()  # assign ticket.id

    result = run_agent(
        subject=subject,
        body=body,
        customer_id=customer_id,
        provider=provider,
        registry=registry,
    )

    for step in result.steps:
        session.add(
            DecisionLog(
                ticket_id=ticket.id,
                step=step.step,
                kind=step.kind,
                tool_name=step.tool_name,
                tool_args=step.tool_args,
                tool_result=step.tool_result,
                content=step.content,
                tokens=step.tokens,
                cost_usd=step.cost_usd,
                latency_ms=step.latency_ms,
            )
        )

    d = result.decision
    # Map the agent's decision to an allowed action (code guardrails).
    guardrail = check_guardrails(
        d.category,
        d.confidence,
        subject=subject,
        body=body,
    )
    session.add(
        Resolution(
            ticket_id=ticket.id,
            category=d.category,
            urgency=d.urgency,
            confidence=d.confidence,
            action=guardrail.action,
            draft_response=d.draft_response,
            reasoning=d.reasoning,
            steps_taken=len(result.steps),
            total_tokens=result.total_tokens,
            cost_usd=result.total_cost_usd,
            latency_ms=result.total_latency_ms,
            model_tier=route.tier if route else None,
            model_name=model_name,
            route_reason=route.reason if route else None,
        )
    )

    ticket.status = "escalated" if result.hit_step_limit else "triaged"
    session.commit()
    session.refresh(ticket)
    return ticket
