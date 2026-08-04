"""Postgres/pgvector persistence for knowledge chunks."""

from __future__ import annotations

from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.config import settings
from app.rag.embeddings import EMBEDDING_DIMENSIONS

_engine: Engine | None = None


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{v:.8f}" for v in values) + "]"


def get_rag_engine() -> Engine:
    global _engine
    if _engine is None:
        url = (settings.rag_database_url or "").strip()
        if not url:
            raise RuntimeError("RAG_DATABASE_URL is not configured")
        # Transaction pooler (port 6543) does not support prepared statements
        # the same way as a direct connection — disable them.
        _engine = create_engine(
            url,
            pool_pre_ping=True,
            connect_args={"prepare_threshold": None},
        )
    return _engine


def reset_rag_engine() -> None:
    """Drop the cached engine (used in tests)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None


def ensure_schema(engine: Engine | None = None) -> None:
    eng = engine or get_rag_engine()
    with eng.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS knowledge_chunks (
                    id BIGSERIAL PRIMARY KEY,
                    title TEXT NOT NULL UNIQUE,
                    content TEXT NOT NULL,
                    embedding vector({EMBEDDING_DIMENSIONS}) NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
    # Optional ANN index in its own transaction so failure never undoes the table.
    try:
        with eng.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS knowledge_chunks_embedding_idx
                    ON knowledge_chunks
                    USING hnsw (embedding vector_cosine_ops)
                    """
                )
            )
    except Exception:  # noqa: BLE001 — sequential scan is fine for seed size
        pass


def upsert_chunk(
    title: str,
    content: str,
    embedding: list[float],
    *,
    engine: Engine | None = None,
) -> None:
    eng = engine or get_rag_engine()
    lit = _vector_literal(embedding)
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO knowledge_chunks (title, content, embedding)
                VALUES (:title, :content, CAST(:embedding AS vector))
                ON CONFLICT (title) DO UPDATE SET
                    content = EXCLUDED.content,
                    embedding = EXCLUDED.embedding,
                    updated_at = NOW()
                """
            ),
            {"title": title, "content": content, "embedding": lit},
        )


def similarity_search(
    query_embedding: list[float],
    *,
    limit: int = 3,
    engine: Engine | None = None,
) -> list[dict[str, Any]]:
    eng = engine or get_rag_engine()
    lit = _vector_literal(query_embedding)
    with eng.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                    title,
                    content,
                    1 - (embedding <=> CAST(:embedding AS vector)) AS score
                FROM knowledge_chunks
                ORDER BY embedding <=> CAST(:embedding AS vector)
                LIMIT :limit
                """
            ),
            {"embedding": lit, "limit": limit},
        ).mappings().all()
    return [
        {
            "title": row["title"],
            "content": row["content"],
            "score": float(row["score"]) if row["score"] is not None else 0.0,
        }
        for row in rows
    ]
