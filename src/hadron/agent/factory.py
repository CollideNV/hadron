"""Agent backend factory — creates the appropriate backend from configuration."""

from __future__ import annotations

import os
from typing import Any


def create_agent_backend(
    backend_name: str | None = None,
    *,
    anthropic_api_key: str = "",
    gemini_api_key: str = "",
    openai_api_key: str = "",
    opencode_base_url: str = "",
    **kwargs: Any,
) -> Any:
    """Create an agent backend by name.

    Args:
        backend_name: One of "claude", "gemini", "openai", "opencode".
            Defaults to ``HADRON_AGENT_BACKEND`` env var, or "claude".
        anthropic_api_key: API key for Claude backend.
        gemini_api_key: API key for Gemini backend.
        openai_api_key: API key for OpenAI backend.
        opencode_base_url: Base URL for OpenCode backend.

    Returns:
        An agent backend instance implementing the AgentBackend protocol.

    Raises:
        ImportError: If the required optional dependency is not installed.
        ValueError: If the backend name is unknown.
    """
    name = backend_name or os.environ.get("HADRON_AGENT_BACKEND", "claude")
    name = name.lower().strip()

    if name == "claude":
        from hadron.agent.claude import ClaudeAgentBackend
        return ClaudeAgentBackend(api_key=anthropic_api_key or None)

    if name == "openai":
        from hadron.agent.openai_backend import OpenAIAgentBackend
        return OpenAIAgentBackend(api_key=openai_api_key or None)

    if name == "gemini":
        from hadron.agent.gemini import GeminiAgentBackend
        return GeminiAgentBackend(api_key=gemini_api_key or None)

    if name == "opencode" or name.startswith("opencode:"):
        from hadron.agent.opencode import OpenCodeAgentBackend
        return OpenCodeAgentBackend(base_url=opencode_base_url or None)

    raise ValueError(
        f"Unknown agent backend: {name!r}. "
        f"Supported backends: claude, openai, gemini, opencode"
    )
