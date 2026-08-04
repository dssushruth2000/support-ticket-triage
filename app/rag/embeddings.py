"""Gemini embedding helpers for RAG ingest and query."""

from __future__ import annotations

from google import genai
from google.genai import types

from app.config import settings

# Fixed output size so the pgvector column stays stable across re-ingests.
EMBEDDING_DIMENSIONS = 768


def embed_texts(texts: list[str], *, task: str = "retrieval_document") -> list[list[float]]:
    """Embed one or more texts with the configured Gemini embedding model.

    ``task`` is a free-text hint prepended for retrieval quality (document vs query).
    """
    if not texts:
        return []
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is required for RAG embeddings")

    client = genai.Client(api_key=settings.gemini_api_key)
    # gemini-embedding-001 accepts task_type; newer models ignore it and use
    # prompt-style instructions — either way we keep the string for clarity.
    contents = [f"{task}: {t}" if task else t for t in texts]
    result = client.models.embed_content(
        model=settings.embedding_model,
        contents=contents,
        config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIMENSIONS),
    )
    if not result.embeddings:
        raise RuntimeError("embedding API returned no vectors")
    vectors: list[list[float]] = []
    for emb in result.embeddings:
        values = list(emb.values or [])
        if len(values) != EMBEDDING_DIMENSIONS:
            raise RuntimeError(
                f"expected {EMBEDDING_DIMENSIONS}-d embedding, got {len(values)}"
            )
        vectors.append(values)
    return vectors


def embed_query(query: str) -> list[float]:
    return embed_texts([query], task="retrieval_query")[0]


def embed_document(title: str, content: str) -> list[float]:
    return embed_texts([f"{title}\n\n{content}"], task="retrieval_document")[0]
