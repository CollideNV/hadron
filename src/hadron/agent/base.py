"""Agent backend protocol and shared data types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Awaitable, Protocol


# Callback type: (tool_name, tool_input, result_snippet) -> None
OnToolCall = Callable[[str, dict[str, Any], str], Awaitable[None]]

# Rich event callback: (event_type, data_dict) -> None
OnAgentEvent = Callable[[str, dict[str, Any]], Awaitable[None]]


# ---------------------------------------------------------------------------
# Model → provider mapping
# ---------------------------------------------------------------------------

def provider_for_model(model: str) -> str:
    """Return the provider name for a model identifier.

    Falls back to heuristic prefix matching if the model is not in the
    explicit map.
    """
    from hadron.config.providers import get_provider_for_model as _get
    provider = _get(model)
    if provider:
        return provider
    
    # Heuristic fallback
    if model.startswith("claude"):
        return "anthropic"
    if model.startswith("gemini"):
        return "gemini"
    
    return "unknown"


@dataclass
class AgentTask:
    """Task definition for an agent invocation."""

    role: str  # e.g. "spec_writer", "code_writer", "reviewer"
    system_prompt: str
    user_prompt: str
    working_directory: str | None = None
    allowed_tools: list[str] = field(default_factory=lambda: [
        "read_file", "write_file", "list_directory", "run_command"
    ])
    model: str = "gemini-3-pro-preview"
    max_tokens: int = 16384
    max_tool_rounds: int = 50
    on_tool_call: OnToolCall | None = None
    on_event: OnAgentEvent | None = None
    nudge_poll: Callable[[], Awaitable[str | None]] | None = None


@dataclass
class AgentResult:
    """Result from an agent invocation."""

    output: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    conversation: list[dict[str, Any]] = field(default_factory=list)
    round_count: int = 0


@dataclass
class AgentEvent:
    """Streaming event from an agent."""

    event_type: str  # text_delta | tool_use | tool_result | done
    data: dict[str, Any] = field(default_factory=dict)


class AgentBackend(Protocol):
    """Protocol for agent backend implementations.

    Every concrete backend must expose a ``name`` so the provider-chain
    machinery can route tasks to the right backend based on the model's
    provider.
    """

    @property
    def name(self) -> str:
        """Short provider identifier, e.g. ``'anthropic'``, ``'gemini'``."""
        ...

    async def execute(self, task: AgentTask) -> AgentResult: ...

    def stream(self, task: AgentTask) -> AsyncIterator[AgentEvent]:
        """Return an async iterator of events.

        Implementations are typically async generator functions — they
        return an AsyncGenerator (which is an AsyncIterator) directly
        without needing to be awaited.  Callers use::

            async for event in backend.stream(task):
                ...
        """
        ...
