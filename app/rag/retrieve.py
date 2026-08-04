"""High-level RAG retrieval used by the knowledge-base tool."""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from app.rag.embeddings import embed_query
from app.rag.store import similarity_search

logger = logging.getLogger(__name__)


def rag_enabled() -> bool:
    return bool(settings.enable_rag and (settings.rag_database_url or "").strip())


def rag_search(query: str, *, limit: int = 3) -> list[dict[str, Any]]:
    """Return top-k chunks for ``query``. Raises on configuration / API errors."""
    if not rag_enabled():
        raise RuntimeError("RAG is not enabled or RAG_DATABASE_URL is empty")
    vector = embed_query(query)
    return similarity_search(vector, limit=limit)
