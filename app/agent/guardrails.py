"""The guardrail layer.

Hard rules in plain Python (deliberately *not* prompts) that map the agent's
decision to what the system is actually allowed to *do* with it. The agent
proposes; the guardrails dispose.

This is the project's answer to OWASP LLM06 "Excessive Agency": the model never
autonomously performs an irreversible/high-risk action. Instead, least-privilege
routing gates every decision behind explicit thresholds and human checkpoints:

* High-risk money/account actions (billing, refund, cancellation) are *always*
  escalated to a human, regardless of how confident the model is.
* Ticket text with money-action cues (e.g. "want a refund", "cancel my plan")
  also escalates — defense in depth when the model mis-labels the category.
* Low-confidence decisions are drafted for a human to review before sending.
* Only demonstrably safe, low-risk, high-confidence categories may auto-respond.
* Everything else falls through to the cautious default (draft for review).

Because these are ordinary Python rules, they are trivially unit-testable and
auditable — you can prove "billing never auto-sends" without invoking the LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --- Possible actions -------------------------------------------------------

AUTO_RESPOND = "auto_respond"
DRAFT_FOR_REVIEW = "draft_for_review"
ESCALATE_TO_HUMAN = "escalate_to_human"

# --- Policy configuration ---------------------------------------------------

# Categories that touch money or account lifecycle: never automated.
HIGH_RISK_CATEGORIES = frozenset({"billing", "refund", "cancellation"})

# Low-risk categories eligible for automation when confidence is high enough.
AUTO_RESPOND_CATEGORIES = frozenset({"password_reset", "faq"})

# Minimum confidence to auto-respond on a low-risk category.
AUTO_RESPOND_MIN_CONFIDENCE = 0.9

# Below this, a human reviews the draft first.
REVIEW_MIN_CONFIDENCE = 0.75

# Phrases that imply a money / lifecycle *action* (not a policy FAQ lookup).
# Used as a second line of defense when the model mis-classifies the ticket.
_HIGH_RISK_ACTION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\b(want|need|request|get|ask for|looking for|obtain)\b.{0,24}\b(refund|rebate|rebates|compensation)\b",
        r"\b(refund|rebate|rebates|compensation)\b.{0,24}\b(please|now|my|me|this|status)\b",
        r"\breimburse(ment)?\b.{0,16}\b(me|my|for)\b",
        r"\bcancel(ling|ation)?\b.{0,24}\b(my|the|subscription|plan|order|account)\b",
        r"\b(subscription|plan|order|account)\b.{0,24}\bcancel",
        r"\b(cancellation|withdrawal)\s+fees?\b",
        r"\bcharged?\s+(twice|two times|again|duplicate)\b",
        r"\bdouble[- ]?(charged?|billed?)\b",
        r"\b(overcharged|billing error|incorrect charge|wrong charge)\b",
        r"\bpayment\s+issue\b",
        r"\bpayment\s+(problem|error|fail)",
        r"\bissues?\b.{0,40}\b(online\s+)?payments?\b",
        r"\b(online\s+)?payments?\b.{0,40}\bissues?\b",
        r"\bfailed\s+payment\b",
    )
)


@dataclass(frozen=True)
class GuardrailResult:
    """The guardrail verdict for a single agent decision."""

    action: str
    reason: str


def ticket_has_high_risk_action_cues(subject: str = "", body: str = "") -> bool:
    """True when the ticket text asks for a money/lifecycle action."""
    text = f"{subject}\n{body}".strip()
    if not text:
        return False
    return any(p.search(text) for p in _HIGH_RISK_ACTION_PATTERNS)


def check_guardrails(
    category: str | None,
    confidence: float | None,
    *,
    subject: str = "",
    body: str = "",
) -> GuardrailResult:
    """Map an agent decision to the action the system is allowed to take.

    The rules are evaluated in priority order so the safest constraint always
    wins:

    1. High-risk category OR money-action cues in ticket text
       -> escalate_to_human   (even at confidence 1.0)
    2. Confidence < 0.75       -> draft_for_review
    3. Safe category + >= 0.9  -> auto_respond
    4. Otherwise               -> draft_for_review    (cautious default)

    ``confidence`` of ``None`` is treated as zero trust, so anything without a
    parseable confidence is drafted for review rather than sent.
    """
    cat = (category or "").strip().lower()
    conf = confidence if confidence is not None else 0.0

    # Rule 1a — irreversible / financial categories always need a human.
    if cat in HIGH_RISK_CATEGORIES:
        return GuardrailResult(
            action=ESCALATE_TO_HUMAN,
            reason=(
                f"Category '{cat}' is high-risk (money/account lifecycle); "
                "escalated to a human regardless of confidence."
            ),
        )

    # Rule 1b — defense in depth: escalate when the ticket *text* asks for a
    # money/lifecycle action even if the model labeled it faq/password_reset.
    if ticket_has_high_risk_action_cues(subject, body):
        return GuardrailResult(
            action=ESCALATE_TO_HUMAN,
            reason=(
                "Ticket text contains money/account-lifecycle action cues; "
                "escalated to a human regardless of predicted category."
            ),
        )

    # Rule 2 — low trust means a human checks the draft before it goes out.
    if conf < REVIEW_MIN_CONFIDENCE:
        return GuardrailResult(
            action=DRAFT_FOR_REVIEW,
            reason=(
                f"Confidence {conf:.2f} is below the review threshold "
                f"{REVIEW_MIN_CONFIDENCE}; drafted for human review."
            ),
        )

    # Rule 3 — safe, low-risk, high-confidence categories may auto-respond.
    if cat in AUTO_RESPOND_CATEGORIES and conf >= AUTO_RESPOND_MIN_CONFIDENCE:
        return GuardrailResult(
            action=AUTO_RESPOND,
            reason=(
                f"Category '{cat}' is low-risk and confidence {conf:.2f} meets "
                f"the auto-respond threshold {AUTO_RESPOND_MIN_CONFIDENCE}."
            ),
        )

    # Rule 4 — default to caution.
    return GuardrailResult(
        action=DRAFT_FOR_REVIEW,
        reason="No auto-respond rule matched; defaulting to human review.",
    )
