"""Phase 2 — the guardrail layer.

Hard rules in plain Python (deliberately *not* prompts) that map the agent's
decision to what the system is actually allowed to *do* with it. The agent
proposes; the guardrails dispose.

This is the project's answer to OWASP LLM06 "Excessive Agency": the model never
autonomously performs an irreversible/high-risk action. Instead, least-privilege
routing gates every decision behind explicit thresholds and human checkpoints:

* High-risk money/account actions (billing, refund, cancellation) are *always*
  escalated to a human, regardless of how confident the model is.
* Low-confidence decisions are drafted for a human to review before sending.
* Only demonstrably safe, low-risk, high-confidence categories may auto-respond.
* Everything else falls through to the cautious default (draft for review).

Because these are ordinary Python rules, they are trivially unit-testable and
auditable — you can prove "billing never auto-sends" without invoking the LLM.
"""

from __future__ import annotations

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


@dataclass(frozen=True)
class GuardrailResult:
    """The guardrail verdict for a single agent decision."""

    action: str
    reason: str


def check_guardrails(
    category: str | None, confidence: float | None
) -> GuardrailResult:
    """Map an agent decision to the action the system is allowed to take.

    The rules are evaluated in priority order so the safest constraint always
    wins:

    1. High-risk category      -> escalate_to_human   (even at confidence 1.0)
    2. Confidence < 0.75       -> draft_for_review
    3. Safe category + >= 0.9  -> auto_respond
    4. Otherwise               -> draft_for_review    (cautious default)

    ``confidence`` of ``None`` is treated as zero trust, so anything without a
    parseable confidence is drafted for review rather than sent.
    """
    cat = (category or "").strip().lower()
    conf = confidence if confidence is not None else 0.0

    # Rule 1 — irreversible / financial actions always need a human. This check
    # comes first so no confidence value can ever bypass it.
    if cat in HIGH_RISK_CATEGORIES:
        return GuardrailResult(
            action=ESCALATE_TO_HUMAN,
            reason=(
                f"Category '{cat}' is high-risk (money/account lifecycle); "
                "escalated to a human regardless of confidence."
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
