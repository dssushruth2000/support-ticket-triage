"""Phase 4 — cheap vs. strong model routing.

A lightweight heuristic glances at the ticket *before* the agent loop and picks
a model tier. Easy, low-risk tickets (FAQ / password reset) go to the cheap
model; money / lifecycle / technical / ambiguous tickets go to the stronger one.

This is deliberately plain code (keywords + category guesses), not another LLM
call — routing itself should be free and instant. The provider abstraction is
the seam that actually swaps models.
"""

from __future__ import annotations

from dataclasses import dataclass

# Tiers the rest of the system understands.
CHEAP = "cheap"
STRONG = "strong"

# Keywords that suggest a high-stakes / complex ticket -> strong model.
_STRONG_HINTS = (
    "charg",
    "billed",
    "invoice",
    "payment",
    "refund",
    "cancel",
    "subscription",
    "outage",
    "down",
    "error",
    "crash",
    "bug",
    "not working",
    "500",
    "timeout",
    "hack",
    "breach",
    "unauthorized",
    "fraud",
    "lawsuit",
    "legal",
)

# Keywords that suggest a safe, routine ticket -> cheap model.
_CHEAP_HINTS = (
    "password",
    "reset",
    "forgot",
    "log in",
    "login",
    "sign in",
    "business hours",
    "hours of operation",
    "how do i",
    "where can i",
    "what are your",
    "newsletter",
    "unsubscribe",
)


@dataclass(frozen=True)
class RouteDecision:
    """Which model tier to use for a ticket, and why."""

    tier: str  # "cheap" | "strong"
    reason: str
    guessed_category: str | None = None


def route_ticket(subject: str, body: str) -> RouteDecision:
    """Pick cheap vs strong from the ticket text alone (no LLM call)."""
    text = f"{subject}\n{body}".lower()

    # Strong signals win first — never send money/outage tickets to the cheap model.
    if any(h in text for h in _STRONG_HINTS):
        guess = _guess_category(text)
        return RouteDecision(
            tier=STRONG,
            reason=f"Matched high-complexity/high-risk cues; routing to strong model "
            f"(guessed ~{guess or 'complex'}).",
            guessed_category=guess,
        )

    if any(h in text for h in _CHEAP_HINTS):
        guess = _guess_category(text)
        return RouteDecision(
            tier=CHEAP,
            reason=f"Matched routine/low-risk cues; routing to cheap model "
            f"(guessed ~{guess or 'faq'}).",
            guessed_category=guess or "faq",
        )

    # Ambiguous -> strong (pay a bit more rather than mis-handle).
    return RouteDecision(
        tier=STRONG,
        reason="No clear cheap-path signal; defaulting to strong model.",
        guessed_category=None,
    )


def _guess_category(text: str) -> str | None:
    if any(w in text for w in ("password", "reset", "log in", "login", "sign in")):
        return "password_reset"
    if any(w in text for w in ("refund",)):
        return "refund"
    if any(w in text for w in ("cancel",)):
        return "cancellation"
    if any(w in text for w in ("charg", "billed", "invoice", "payment", "subscription")):
        return "billing"
    if any(w in text for w in ("outage", "down", "error", "crash", "bug", "not working")):
        return "technical"
    if any(w in text for w in ("business hours", "how do i", "what are your", "newsletter")):
        return "faq"
    return None
