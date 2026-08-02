"""Tests for the agent reasoning loop (with the deterministic mock provider)."""

from __future__ import annotations

from app.agent.llm import MockProvider
from app.agent.loop import run_agent
from app.tools import build_default_registry


def _run(subject: str, body: str, customer_id: str | None = None):
    return run_agent(subject, body, customer_id, MockProvider(), build_default_registry())


def _tools_called(result) -> list[str]:
    return [s.tool_name for s in result.steps if s.kind == "tool"]


def test_billing_ticket_gathers_account_and_policy_then_decides():
    result = _run(
        "Charged twice for my subscription",
        "I was charged twice this month. customer_id: CUST-1001",
        "CUST-1001",
    )
    called = _tools_called(result)
    assert "get_account_orders" in called
    assert "search_knowledge_base" in called
    assert result.decision.category == "billing"
    assert result.decision.draft_response
    assert 0.0 <= result.decision.confidence <= 1.0


def test_password_ticket_classified_as_password_reset():
    result = _run("Can't log in", "I forgot my password, how do I reset it?")
    assert result.decision.category == "password_reset"
    assert "search_knowledge_base" in _tools_called(result)


def test_technical_ticket_checks_system_status():
    result = _run("Dashboard down", "The dashboard shows an error and won't load. Outage?")
    assert result.decision.category == "technical"
    assert "check_system_status" in _tools_called(result)


def test_faq_ticket_is_low_urgency():
    result = _run("Business hours?", "What are your support business hours?")
    assert result.decision.category == "faq"
    assert result.decision.urgency == "low"


def test_loop_produces_final_step_and_metrics():
    result = _run("Business hours?", "What are your support business hours?")
    assert result.steps[-1].kind == "final"
    assert result.total_tokens > 0
    assert not result.hit_step_limit


def test_loop_respects_step_limit():
    result = run_agent(
        "Charged twice",
        "billing issue customer_id: CUST-1001",
        "CUST-1001",
        MockProvider(),
        build_default_registry(),
        max_steps=1,  # too few steps to reach a final decision
    )
    assert result.hit_step_limit is True
    assert result.decision.category == "other"
