"""Ingest seed knowledge docs into Supabase pgvector.

Usage (from project root, with RAG env configured)::

    python -m app.rag.ingest
"""

from __future__ import annotations

import logging
import sys

from app.config import settings
from app.rag.embeddings import embed_document
from app.rag.seed_docs import SEED_DOCUMENTS
from app.rag.store import ensure_schema, upsert_chunk

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    if not settings.enable_rag:
        logger.error("Set ENABLE_RAG=true in .env before ingesting.")
        return 1
    if not (settings.rag_database_url or "").strip():
        logger.error("Set RAG_DATABASE_URL to your Supabase pooler URL.")
        return 1
    if not settings.gemini_api_key:
        logger.error("GEMINI_API_KEY is required to embed documents.")
        return 1

    logger.info(
        "Ingesting %d docs with model=%s into RAG DB…",
        len(SEED_DOCUMENTS),
        settings.embedding_model,
    )
    ensure_schema()
    for doc in SEED_DOCUMENTS:
        title = doc["title"]
        content = doc["content"]
        logger.info("  embedding: %s", title)
        vector = embed_document(title, content)
        upsert_chunk(title, content, vector)
    logger.info("Done. %d chunks upserted.", len(SEED_DOCUMENTS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
