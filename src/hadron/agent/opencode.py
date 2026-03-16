"""OpenCode agent backend — local models via OpenAI-compatible API."""

from __future__ import annotations

import os

from hadron.agent.openai_backend import OpenAIAgentBackend

_DEFAULT_BASE_URL = "http://localhost:11434/v1"


class OpenCodeAgentBackend(OpenAIAgentBackend):
    """Agent backend for local OpenAI-compatible APIs (ollama, vllm, etc.).

    Thin subclass of OpenAIAgentBackend that defaults to a local base_url
    and registers zero cost for local models.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        resolved_url = (
            base_url
            or os.environ.get("HADRON_OPENCODE_BASE_URL")
            or _DEFAULT_BASE_URL
        )
        # Local models often don't need a real API key
        resolved_key = api_key or os.environ.get("HADRON_OPENCODE_API_KEY") or "not-needed"
        super().__init__(api_key=resolved_key, base_url=resolved_url)
