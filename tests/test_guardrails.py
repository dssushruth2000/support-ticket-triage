"""Tests for the Phase 2 guardrail layer.

These are pure-function tests (no LLM, no DB) proving the safety rules hold,
plus one end-to-end test through the service layer proving a billing ticket's
resolution is never marked ``auto_respond``.
"""

from __future__ import annotations

import pytest

from app.agent.guardrails import (
    AUTO_RESPOND,
    DRAFT_FOR_REVIEW,
    ESCALATE_TO_HUMAN,
    HIGH_RISK_CATEGORIES,
    check_guardrails,
)
from app.service import triage_ticket


# --- Rule 1: high-risk categories always escalate --------------------------


@pytest.mark.parametrize("category", sorted(HIGH_RISK_CATEGORIES))
def test_high_risk_categories_always_escalate(category):
    # Even at maximum confidence, money/account actions never auto-send.
    result = check_guardrails(category, 1.0)
    assert result.action == ESCALATE_TO_HUMAN


def test_billing_never_auto_responds_at_any_confidence():
    for conf in (0.0, 0.5, 0.75, 0.9, 0.99, 1.0):
        assert check_guardrails("billing", conf).action == ESCALATE_TO_HUMAN


def test_high_risk_check_is_case_insensitive():
    assert check_guardrails("Billing", 0.95).action == ESCALATE_TO_HUMAN
    assert check_guardrails("REFUND", 0.95).action == ESCALATE_TO_HUMAN


# --- Rule 2: low confidence drafts for review ------------------------------


def test_low_confidence_drafts_for_review():
    assert check_guardrails("faq", 0.5).action == DRAFT_FOR_REVIEW
    assert check_guardrails("password_reset", 0.74).action == DRAFT_FOR_REVIEW


def test_none_confidence_is_treated_as_zero_trust():
    assert check_guardrails("faq", None).action == DRAFT_FOR_REVIEW


# --- Rule 3: safe, high-confidence categories auto-respond -----------------


def test_safe_high_confidence_auto_responds():
    assert check_guardrails("password_reset", 0.9).action == AUTO_RESPOND
    assert check_guardrails("faq", 0.95).action == AUTO_RESPOND


def test_auto_respond_threshold_is_inclusive_at_0_9():
    assert check_guardrails("faq", 0.9).action == AUTO_RESPOND
    # Just under the threshold falls back to review.
    assert check_guardrails("faq", 0.89).action == DRAFT_FOR_REVIEW


# --- Rule 4: cautious default ----------------------------------------------


def test_unknown_high_confidence_category_defaults_to_review():
    # A non-high-risk, non-auto-respond category (e.g. technical) is drafted.
    assert check_guardrails("technical", 0.95).action == DRAFT_FOR_REVIEW
    assert check_guardrails("account", 0.99).action == DRAFT_FOR_REVIEW
    assert check_guardrails("other", 1.0).action == DRAFT_FOR_REVIEW


# --- End-to-end through the service ----------------------------------------


def test_billing_ticket_resolution_is_escalated(session):
    ticket = triage_ticket(
        session,
        subject="Charged twice for my subscription",
        body="I was charged twice this month. customer_id: CUST-1001",
        customer_id="CUST-1001",
    )
    assert ticket.resolution.category == "billing"
    # The guardrail must have escalated it — never an auto-send for billing.
    assert ticket.resolution.action == ESCALATE_TO_HUMAN
    assert ticket.resolution.action != AUTO_RESPOND


def test_password_reset_ticket_resolution_auto_responds(session):
    ticket = triage_ticket(
        session,
        subject="Can't log in",
        body="I forgot my password, how do I reset it?",
    )
    assert ticket.resolution.category == "password_reset"
    assert ticket.resolution.action == AUTO_RESPOND
