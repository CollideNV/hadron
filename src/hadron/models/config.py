"""Configuration models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from hadron.config.defaults import DEFAULT_WORKSPACE_DIR


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
    workspace_dir: str = Field(
        default=DEFAULT_WORKSPACE_DIR,
        description="Root directory for git clones and worktrees.",
    )
    agent_backend: str = Field(
        default="claude",
        description="Agent backend to use: claude, openai, gemini, opencode.",
    )
    gemini_api_key: str = Field(
        default="",
        description="Google Gemini API key for Gemini agent backend.",
    )
    openai_api_key: str = Field(
        default="",
        description="OpenAI API key for OpenAI agent backend.",
    )
    opencode_base_url: str = Field(
        default="",
        description="Base URL for the OpenCode server (opencode serve).",
    )
    opencode_provider_id: str = Field(
        default="",
        description="OpenCode provider ID (e.g. 'ollama', 'anthropic').",
    )
    controller_host: str = Field(default="0.0.0.0")
    controller_port: int = Field(default=8000)
    log_level: str = Field(default="INFO")
    log_format: str = Field(
        default="text",
        description="Log output format: 'text' (colored, human-friendly) or 'json' (structured).",
    )
    otel_enabled: bool = Field(
        default=False,
        description="Enable OpenTelemetry tracing. Requires [observability] extra.",
    )
    otlp_endpoint: str = Field(
        default="http://localhost:4317",
        description="OTLP gRPC endpoint for trace export.",
    )
    embed_sse: bool = Field(
        default=True,
        description="Embed SSE event routes in the controller. Set to false when running a separate SSE gateway.",
    )
    embed_orchestrator: bool = Field(
        default=True,
        description="Embed orchestrator mutation routes in the controller. Set to false when running a separate orchestrator.",
    )
