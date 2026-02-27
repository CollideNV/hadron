"""Agent backend protocol and shared data types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Awaitable, Protocol


# Callback type: (tool_name, tool_input, result_snippet) -> None
OnToolCall = Callable[[str, dict[str, Any], str], Awaitable[None]]

# Rich event callback: (event_type, data_dict) -> None
OnAgentEvent = Callable[[str, dict[str, Any]], Awaitable[None]]


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
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 16384
    max_tool_rounds: int = 50
    on_tool_call: OnToolCall | None = None
    on_event: OnAgentEvent | None = None
    nudge_poll: Callable[[], Awaitable[str | None]] | None = None
    # Three-phase execution: explore (read-only) → plan (single call) → act (full tools)
    explore_model: str = ""  # Empty = skip explore phase
    plan_model: str = ""  # Empty = skip plan phase
    explore_max_rounds: int = 20
    explore_tools: list[str] = field(default_factory=lambda: ["read_file", "list_directory"])


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
    """Protocol for agent backend implementations."""

    async def execute(self, task: AgentTask) -> AgentResult: ...

    async def stream(self, task: AgentTask) -> AsyncIterator[AgentEvent]: ...
