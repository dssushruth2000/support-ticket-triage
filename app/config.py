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

    # Phase 4 — cheap vs strong routing (Gemini only; mock still records the tier).
    enable_model_routing: bool = True
    gemini_model_cheap: str = "gemini-flash-lite-latest"
    gemini_model_strong: str = "gemini-flash-latest"

    # Database. Defaults to a local SQLite file; swap for a Postgres/Supabase
    # connection string with no code changes.
    database_url: str = "sqlite:///./support_triage.db"

    # Agent loop: hard cap on reasoning/tool iterations.
    max_agent_steps: int = 6


settings = Settings()
