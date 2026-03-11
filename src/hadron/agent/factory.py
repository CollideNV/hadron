"""Agent backend factory — routes to the correct backend by model name.

The architecture (§9) specifies pluggable agent backends with provider chains.
This module provides the factory function that maps a model name to the
correct backend implementation.
"""

from __future__ import annotations

from hadron.agent.base import AgentBackend


# Prefixes that identify which backend owns a model.
_GEMINI_PREFIXES = ("gemini-",)
_CLAUDE_PREFIXES = ("claude-",)


def is_gemini_model(model: str) -> bool:
    """Return True if *model* should be handled by the Gemini backend."""
    return any(model.startswith(p) for p in _GEMINI_PREFIXES)


def is_claude_model(model: str) -> bool:
    """Return True if *model* should be handled by the Claude backend."""
    return any(model.startswith(p) for p in _CLAUDE_PREFIXES)


def get_backend(
    model: str,
    *,
    anthropic_api_key: str = "",
    google_api_key: str = "",
) -> AgentBackend:
    """Create the appropriate AgentBackend for *model*.

    Raises ``ValueError`` if the model prefix is not recognised.
    """
    if is_claude_model(model):
        from hadron.agent.claude import ClaudeAgentBackend

        return ClaudeAgentBackend(api_key=anthropic_api_key)

    if is_gemini_model(model):
        from hadron.agent.gemini import GeminiAgentBackend

        return GeminiAgentBackend(api_key=google_api_key)

    raise ValueError(
        f"Unrecognised model '{model}'. "
        f"Expected a model starting with one of: {_CLAUDE_PREFIXES + _GEMINI_PREFIXES}"
    )
