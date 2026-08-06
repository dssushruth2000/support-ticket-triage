"""Application configuration, driven by environment variables / .env.

Everything has a sensible default so the project runs with zero setup:
the mock LLM provider plus a local SQLite database.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM provider: "mock" (default, no key) or "gemini".
    llm_provider: str = "mock"
    gemini_api_key: str = ""
    # Default / fallback model when routing is off.
    gemini_model: str = "gemini-flash-lite-latest"

    # Cheap vs strong routing (Gemini only; mock still records the tier).
    enable_model_routing: bool = True
    gemini_model_cheap: str = "gemini-flash-lite-latest"
    gemini_model_strong: str = "gemini-flash-latest"

    # Database. Defaults to a local SQLite file; swap for a Postgres/Supabase
    # connection string with no code changes. Tickets/logs stay here.
    database_url: str = "sqlite:///./support_triage.db"

    # RAG over Supabase pgvector (separate from ticket DB).
    # When disabled or misconfigured, search_knowledge_base falls back to
    # in-memory keyword matching so offline demos and tests still work.
    enable_rag: bool = False
    rag_database_url: str = ""
    embedding_model: str = "gemini-embedding-001"

    # Agent loop: hard cap on reasoning/tool iterations.
    max_agent_steps: int = 6

    # AgentMail — email front door (receive → triage → optional auto-reply).
    agentmail_api_key: str = ""
    agentmail_inbox_username: str = "support-triage"
    agentmail_inbox_id: str = ""
    agentmail_webhook_secret: str = ""
    # When true, send a reply only if guardrails chose auto_respond.
    agentmail_auto_reply: bool = True


settings = Settings()
