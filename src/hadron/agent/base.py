"""Agent backend protocol and shared data types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Awaitable, Protocol

from hadron.config.defaults import DEFAULT_MODEL


# Callback type: (tool_name, tool_input, result_snippet) -> None
OnToolCall = Callable[[str, dict[str, Any], str], Awaitable[None]]

# Rich event callback: (event_type, data_dict) -> None
OnAgentEvent = Callable[[str, dict[str, Any]], Awaitable[None]]


@dataclass
class PhaseConfig:
    """Configuration for the three-phase execution pipeline.

    Controls the explore (read-only) -> plan (single call) -> act (full tools) flow.
    Empty model strings skip the corresponding phase.
    """

    explore_model: str = ""  # Empty = skip explore phase
    plan_model: str = ""  # Empty = skip plan phase
    explore_max_rounds: int = 20
    explore_tools: list[str] = field(default_factory=lambda: ["read_file", "list_directory"])


@dataclass
class AgentCallbacks:
    """Optional callbacks for observability during agent execution."""

    on_tool_call: OnToolCall | None = None
    on_event: OnAgentEvent | None = None
    nudge_poll: Callable[[], Awaitable[str | None]] | None = None


@dataclass
class AgentTask:
    """Task definition for an agent invocation.

    Groups concerns into:
      - Identity: role, prompts
      - Execution: model, tools, limits, working directory
      - Phases: three-phase pipeline config (via PhaseConfig)
      - Callbacks: observability hooks (via AgentCallbacks)
    """

    # Identity
    role: str  # e.g. "spec_writer", "code_writer", "reviewer"
    system_prompt: str
    user_prompt: str

    # Execution
    working_directory: str | None = None
    allowed_tools: list[str] = field(default_factory=lambda: [
        "read_file", "write_file", "delete_file", "list_directory", "run_command"
    ])
    model: str = DEFAULT_MODEL
    max_tokens: int = 16384
    max_tool_rounds: int = 50

    # Phases (three-phase pipeline)
    phases: PhaseConfig = field(default_factory=PhaseConfig)

    # Callbacks (observability)
    callbacks: AgentCallbacks = field(default_factory=AgentCallbacks)

    # --- Convenience accessors for backwards compatibility ---
    @property
    def explore_model(self) -> str:
        return self.phases.explore_model

    @property
    def plan_model(self) -> str:
        return self.phases.plan_model

    @property
    def explore_max_rounds(self) -> int:
        return self.phases.explore_max_rounds

    @property
    def explore_tools(self) -> list[str]:
        return self.phases.explore_tools

    @property
    def on_tool_call(self) -> OnToolCall | None:
        return self.callbacks.on_tool_call

    @property
    def on_event(self) -> OnAgentEvent | None:
        return self.callbacks.on_event

    @property
    def nudge_poll(self) -> Callable[[], Awaitable[str | None]] | None:
        return self.callbacks.nudge_poll


@dataclass
class ModelStats:
    """Per-model usage stats for cost and throttle breakdown."""

    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    throttle_count: int = 0
    throttle_seconds: float = 0.0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    api_calls: int = 0

    def merge(self, other: ModelStats) -> ModelStats:
        """Return a new ModelStats combining self and other."""
        return ModelStats(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cost_usd=self.cost_usd + other.cost_usd,
            throttle_count=self.throttle_count + other.throttle_count,
            throttle_seconds=self.throttle_seconds + other.throttle_seconds,
            cache_creation_tokens=self.cache_creation_tokens + other.cache_creation_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            api_calls=self.api_calls + other.api_calls,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": self.cost_usd,
            "throttle_count": self.throttle_count,
            "throttle_seconds": self.throttle_seconds,
            "cache_creation_tokens": self.cache_creation_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "api_calls": self.api_calls,
        }


def merge_model_breakdowns(
    a: dict[str, dict[str, Any]],
    b: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Merge two model_breakdown dicts, summing stats per model."""
    result = {k: dict(v) for k, v in a.items()}
    for model, stats in b.items():
        if model in result:
            for key in ("input_tokens", "output_tokens", "throttle_count", "cache_creation_tokens", "cache_read_tokens", "api_calls"):
                result[model][key] = result[model].get(key, 0) + stats.get(key, 0)
            for key in ("cost_usd", "throttle_seconds"):
                result[model][key] = result[model].get(key, 0.0) + stats.get(key, 0.0)
        else:
            result[model] = dict(stats)
    return result


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
    model: str = ""
    throttle_count: int = 0
    throttle_seconds: float = 0.0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    model_breakdown: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class CostAccumulator:
    """Accumulates cost/token stats across multiple agent runs."""
    total_cost: float = 0.0
    total_input: int = 0
    total_output: int = 0
    throttle_count: int = 0
    throttle_seconds: float = 0.0
    model_breakdown: dict[str, dict[str, Any]] = field(default_factory=dict)

    def add(self, result: AgentResult) -> None:
        self.total_cost += result.cost_usd
        self.total_input += result.input_tokens
        self.total_output += result.output_tokens
        self.throttle_count += result.throttle_count
        self.throttle_seconds += result.throttle_seconds
        self.model_breakdown = merge_model_breakdowns(self.model_breakdown, result.model_breakdown)

    def to_state_dict(self) -> dict[str, Any]:
        return {
            "cost_input_tokens": self.total_input,
            "cost_output_tokens": self.total_output,
            "cost_usd": self.total_cost,
            "throttle_count": self.throttle_count,
            "throttle_seconds": self.throttle_seconds,
            "model_breakdown": self.model_breakdown,
        }


@dataclass
class AgentEvent:
    """Streaming event from an agent."""

    event_type: str  # text_delta | tool_use | tool_result | done
    data: dict[str, Any] = field(default_factory=dict)


class AgentBackend(Protocol):
    """Protocol for agent backend implementations."""

    async def execute(self, task: AgentTask) -> AgentResult: ...

    async def stream(self, task: AgentTask) -> AsyncIterator[AgentEvent]: ...
