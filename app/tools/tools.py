"""Implementations of the agent's tools.

For Phase 1 these run against small in-memory fixtures so the whole system is
runnable offline. The knowledge-base search here is a simple keyword matcher;
Phase 3 swaps its internals for real RAG over pgvector without changing the
tool's signature or the agent that calls it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

# --- Fake account/order data ------------------------------------------------

_NOW = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)

_ACCOUNTS: dict[str, list[dict[str, Any]]] = {
    # Customer with a genuine duplicate charge (2 hours apart).
    "CUST-1001": [
        {
            "order_id": "ORD-55010",
            "description": "Pro subscription (monthly)",
            "amount_usd": 29.00,
            "charged_at": (_NOW - timedelta(hours=4)).isoformat(),
        },
        {
            "order_id": "ORD-55011",
            "description": "Pro subscription (monthly) - DUPLICATE",
            "amount_usd": 29.00,
            "charged_at": (_NOW - timedelta(hours=2)).isoformat(),
        },
    ],
    "CUST-1002": [
        {
            "order_id": "ORD-40222",
            "description": "Annual plan",
            "amount_usd": 299.00,
            "charged_at": (_NOW - timedelta(days=40)).isoformat(),
        }
    ],
}

# --- Fake knowledge base ----------------------------------------------------

_KNOWLEDGE_BASE: list[dict[str, str]] = [
    {
        "title": "Duplicate charge refund policy",
        "content": (
            "If a customer is charged more than once for the same subscription "
            "within 24 hours, the duplicate charge is eligible for an automatic "
            "refund. Refunds post within 5-7 business days."
        ),
    },
    {
        "title": "How to reset your password",
        "content": (
            "Users can reset their password via the 'Forgot password' link on the "
            "sign-in page. A reset link is emailed and expires after 60 minutes."
        ),
    },
    {
        "title": "Service outage troubleshooting",
        "content": (
            "If the app fails to load, first check the status page. Transient "
            "errors usually resolve within minutes; persistent issues should be "
            "escalated to the on-call engineer."
        ),
    },
    {
        "title": "Cancellation policy",
        "content": (
            "Subscriptions can be cancelled anytime. Cancellations take effect at "
            "the end of the current billing period; no partial-period refunds."
        ),
    },
]


def get_account_orders(customer_id: str) -> dict[str, Any]:
    orders = _ACCOUNTS.get(customer_id, [])
    return {
        "customer_id": customer_id,
        "found": bool(orders),
        "orders": orders,
        "order_count": len(orders),
    }


def search_knowledge_base(query: str) -> dict[str, Any]:
    terms = {t for t in query.lower().split() if len(t) > 2}
    scored: list[tuple[int, dict[str, str]]] = []
    for doc in _KNOWLEDGE_BASE:
        haystack = (doc["title"] + " " + doc["content"]).lower()
        score = sum(1 for t in terms if t in haystack)
        if score:
            scored.append((score, doc))
    scored.sort(key=lambda x: x[0], reverse=True)
    results = [{"title": d["title"], "content": d["content"]} for _, d in scored[:3]]
    return {"query": query, "match_count": len(results), "results": results}


def check_system_status() -> dict[str, Any]:
    return {
        "overall": "operational",
        "components": {
            "api": "operational",
            "dashboard": "operational",
            "billing": "operational",
        },
        "checked_at": _NOW.isoformat(),
    }


def flag_for_escalation(reason: str) -> dict[str, Any]:
    return {"escalated": True, "reason": reason}


def log_resolution(ticket_id: str, outcome: str) -> dict[str, Any]:
    return {"logged": True, "ticket_id": ticket_id, "outcome": outcome}
