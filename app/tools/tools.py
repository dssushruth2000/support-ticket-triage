"""Implementations of the agent's tools.

Account/status tools use in-memory fixtures. Knowledge-base search uses real
RAG (Gemini embeddings + Supabase pgvector) when ENABLE_RAG is on; otherwise
falls back to in-memory keyword matching so offline demos and tests work.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.rag.seed_docs import SEED_DOCUMENTS

logger = logging.getLogger(__name__)

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

# Offline / fallback corpus (same seed used by ``python -m app.rag.ingest``).
_KNOWLEDGE_BASE: list[dict[str, str]] = list(SEED_DOCUMENTS)


def get_account_orders(customer_id: str) -> dict[str, Any]:
    orders = _ACCOUNTS.get(customer_id, [])
    return {
        "customer_id": customer_id,
        "found": bool(orders),
        "orders": orders,
        "order_count": len(orders),
    }


def _keyword_search(query: str) -> dict[str, Any]:
    terms = {t for t in query.lower().split() if len(t) > 2}
    scored: list[tuple[int, dict[str, str]]] = []
    for doc in _KNOWLEDGE_BASE:
        haystack = (doc["title"] + " " + doc["content"]).lower()
        score = sum(1 for t in terms if t in haystack)
        if score:
            scored.append((score, doc))
    scored.sort(key=lambda x: x[0], reverse=True)
    results = [{"title": d["title"], "content": d["content"]} for _, d in scored[:3]]
    return {
        "query": query,
        "match_count": len(results),
        "results": results,
        "source": "keyword",
    }


def search_knowledge_base(query: str) -> dict[str, Any]:
    """Search policy/FAQ docs — RAG when configured, else keyword fallback."""
    try:
        from app.rag.retrieve import rag_enabled, rag_search

        if rag_enabled():
            hits = rag_search(query, limit=3)
            results = [
                {
                    "title": h["title"],
                    "content": h["content"],
                    "score": h.get("score"),
                }
                for h in hits
            ]
            return {
                "query": query,
                "match_count": len(results),
                "results": results,
                "source": "rag",
            }
    except Exception as exc:  # noqa: BLE001 — never crash the agent loop
        logger.warning("RAG search failed; falling back to keyword: %s", exc)

    return _keyword_search(query)


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
