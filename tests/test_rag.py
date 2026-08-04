"""Unit tests for RAG wiring and keyword fallback (no live Supabase required)."""

from __future__ import annotations

from unittest.mock import patch

from app.tools import build_default_registry
from app.tools import tools as tools_mod


def test_search_falls_back_to_keyword_when_rag_disabled():
    reg = build_default_registry()
    with patch("app.rag.retrieve.rag_enabled", return_value=False):
        result = reg.dispatch(
            "search_knowledge_base",
            {"query": "duplicate charge refund policy"},
        )
    assert result["source"] == "keyword"
    assert result["match_count"] >= 1
    assert "refund" in result["results"][0]["content"].lower()


def test_search_uses_rag_when_enabled():
    fake_hits = [
        {
            "title": "Duplicate charge refund policy",
            "content": "Eligible for automatic refund within 24 hours.",
            "score": 0.91,
        }
    ]
    with (
        patch("app.rag.retrieve.rag_enabled", return_value=True),
        patch("app.rag.retrieve.rag_search", return_value=fake_hits),
    ):
        result = tools_mod.search_knowledge_base("charged twice")
    assert result["source"] == "rag"
    assert result["match_count"] == 1
    assert result["results"][0]["title"] == "Duplicate charge refund policy"
    assert result["results"][0]["score"] == 0.91


def test_search_falls_back_when_rag_raises():
    with (
        patch("app.rag.retrieve.rag_enabled", return_value=True),
        patch("app.rag.retrieve.rag_search", side_effect=RuntimeError("db down")),
    ):
        result = tools_mod.search_knowledge_base("password reset link")
    assert result["source"] == "keyword"
    assert result["match_count"] >= 1


def test_rag_enabled_requires_url_and_flag():
    from app.rag.retrieve import rag_enabled

    with patch("app.rag.retrieve.settings") as mock_settings:
        mock_settings.enable_rag = True
        mock_settings.rag_database_url = ""
        assert rag_enabled() is False

        mock_settings.rag_database_url = "postgresql+psycopg://x"
        assert rag_enabled() is True

        mock_settings.enable_rag = False
        assert rag_enabled() is False
