"""Tests for model routing."""

from __future__ import annotations

from app.agent.router import CHEAP, STRONG, route_ticket
from app.service import triage_ticket


def test_password_ticket_routes_cheap():
    d = route_ticket("Can't log in", "I forgot my password, how do I reset it?")
    assert d.tier == CHEAP


def test_billing_ticket_routes_strong():
    d = route_ticket("Charged twice", "I was billed twice this month")
    assert d.tier == STRONG


def test_ambiguous_ticket_defaults_strong():
    d = route_ticket("Hello", "I have a question about something.")
    assert d.tier == STRONG


def test_triage_persists_routing_fields(session):
    ticket = triage_ticket(
        session,
        subject="Can't log in",
        body="I forgot my password, how do I reset it?",
    )
    assert ticket.resolution is not None
    assert ticket.resolution.model_tier == CHEAP
    assert ticket.resolution.route_reason
    assert ticket.resolution.model_name  # mock records the resolved model name
