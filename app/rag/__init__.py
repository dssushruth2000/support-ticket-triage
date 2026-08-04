"""Phase 3b RAG: Gemini embeddings + Supabase pgvector retrieval."""

from __future__ import annotations

from app.rag.retrieve import rag_enabled, rag_search

__all__ = ["rag_enabled", "rag_search"]
