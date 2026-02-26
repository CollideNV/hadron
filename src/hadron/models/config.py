"""Configuration models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BootstrapConfig(BaseModel):
    """Bootstrap configuration loaded from environment variables.

    These are the minimal settings needed to start the controller or worker.
    All pipeline-level config uses hardcoded defaults for MVP.
    """

    postgres_url: str = Field(
        default="postgresql+asyncpg://hadron:hadron@localhost:5432/hadron",
        description="Async SQLAlchemy database URL.",
    )
    postgres_url_sync: str = Field(
        default="postgresql+psycopg://hadron:hadron@localhost:5432/hadron",
        description="Sync database URL for Alembic and langgraph checkpointer.",
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
    )
    anthropic_api_key: str = Field(
        default="",
        description="Anthropic API key for Claude agent backend.",
    )
    gemini_api_key: str = Field(
        default="",
        description="Google Gemini API key for Gemini agent backend.",
    )
    workspace_dir: str = Field(
        default="/tmp/hadron-workspace",
        description="Root directory for git clones and worktrees.",
    )
    controller_host: str = Field(default="0.0.0.0")
    controller_port: int = Field(default=8000)
    log_level: str = Field(default="INFO")
