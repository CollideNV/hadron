"""Abstract base class for agent backends with three-phase orchestration."""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from hadron.agent.base import AgentEvent, AgentResult, AgentTask, ModelStats, OnAgentEvent
from hadron.agent.phases import PhasePromptBuilder
from hadron.agent.tool_loop import ToolLoopConfig, _PhaseResult
from hadron.agent.tools import make_tools

logger = logging.getLogger(__name__)


class _ResultAccumulator:
    """Accumulates stats across explore/plan/act phases."""

    __slots__ = (
        "input_tokens", "output_tokens", "cost", "tool_calls", "conversations",
        "rounds", "throttle_count", "throttle_seconds",
        "cache_creation", "cache_read", "breakdown",
    )

    def __init__(self) -> None:
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost = 0.0
        self.tool_calls: list[dict[str, Any]] = []
        self.conversations: list[dict[str, Any]] = []
        self.rounds = 0
        self.throttle_count = 0
        self.throttle_seconds = 0.0
        self.cache_creation = 0
        self.cache_read = 0
        self.breakdown: dict[str, ModelStats] = {}

    def add(self, result: _PhaseResult, model: str) -> None:
        self.input_tokens += result.input_tokens
        self.output_tokens += result.output_tokens
        self.cost += result.cost_usd
        self.tool_calls.extend(result.tool_calls)
        self.conversations.extend(result.conversation)
        self.rounds += result.round_count
        self.throttle_count += result.throttle_count
        self.throttle_seconds += result.throttle_seconds
        self.cache_creation += result.cache_creation_tokens
        self.cache_read += result.cache_read_tokens
        stats = result.to_model_stats()
        self.breakdown[model] = self.breakdown.get(model, ModelStats()).merge(stats)

    def to_result(self, output: str, model: str) -> AgentResult:
        return AgentResult(
            output=output,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            cost_usd=self.cost,
            tool_calls=self.tool_calls,
            conversation=self.conversations,
            round_count=self.rounds,
            model=model,
            throttle_count=self.throttle_count,
            throttle_seconds=self.throttle_seconds,
            cache_creation_tokens=self.cache_creation,
            cache_read_tokens=self.cache_read,
            model_breakdown={m: s.to_dict() for m, s in self.breakdown.items()},
        )


class BaseAgentBackend:
    """Abstract base class for agent backends.

    Implements three-phase orchestration: Explore → Plan → Act.
    Subclasses override _call_tool_loop, _call_plan, and optionally _compact.
    """

    def __init__(self) -> None:
        self._prompts = PhasePromptBuilder()

    async def execute(self, task: AgentTask) -> AgentResult:
        """Run the agent's three-phase pipeline to completion."""
        acc = _ResultAccumulator()

        if task.on_event:
            await task.on_event("prompt", {"text": task.user_prompt})

        exploration_summary = await self._run_explore_phase(task, acc) if task.explore_model else ""
        plan_text = await self._run_plan_phase(task, acc, exploration_summary) if task.plan_model else ""
        act_result = await self._run_act_phase(task, acc, exploration_summary, plan_text)

        return acc.to_result(act_result.output, task.model)

    async def stream(self, task: AgentTask) -> AsyncIterator[AgentEvent]:
        """Stream agent events. Default: not supported."""
        raise NotImplementedError(f"{type(self).__name__} does not support streaming")
        yield  # Make it a generator  # pragma: no cover

    # ------------------------------------------------------------------
    # Phase orchestration (shared across all backends)
    # ------------------------------------------------------------------

    async def _run_explore_phase(self, task: AgentTask, acc: _ResultAccumulator) -> str:
        if task.on_event:
            await task.on_event("phase_started", {"phase": "explore", "model": task.explore_model})

        result = await self._call_tool_loop(ToolLoopConfig(
            model=task.explore_model,
            system_prompt=self._prompts.build_explore_system(task),
            user_prompt=task.user_prompt,
            tools=make_tools(task.explore_tools, task.working_directory),
            working_dir=task.working_directory or ".",
            max_rounds=task.explore_max_rounds,
            max_tokens=task.max_tokens,
            on_event=task.on_event,
            phase="explore",
        ))
        acc.add(result, task.explore_model)

        if task.on_event:
            await task.on_event("phase_completed", {
                "phase": "explore", "model": task.explore_model,
                "summary_length": len(result.output),
                "rounds": result.round_count,
                "input_tokens": result.input_tokens, "output_tokens": result.output_tokens,
                "cost_usd": result.cost_usd,
                "throttle_count": result.throttle_count, "throttle_seconds": result.throttle_seconds,
                "cache_read_tokens": result.cache_read_tokens,
            })
        logger.info(
            "Explore phase complete: %d rounds, %d input tokens, summary=%d chars",
            result.round_count, result.input_tokens, len(result.output),
        )
        return result.output

    async def _run_plan_phase(self, task: AgentTask, acc: _ResultAccumulator, exploration_summary: str) -> str:
        if task.on_event:
            await task.on_event("phase_started", {"phase": "plan", "model": task.plan_model})

        result = await self._call_plan(
            model=task.plan_model,
            system_prompt=self._prompts.build_plan_system(task),
            user_prompt=self._prompts.build_plan_user(task, exploration_summary),
            max_tokens=task.max_tokens,
        )
        acc.add(result, task.plan_model)

        if task.on_event and result.output:
            await task.on_event("output", {"text": result.output, "round": 0})
        if task.on_event:
            await task.on_event("phase_completed", {
                "phase": "plan", "model": task.plan_model,
                "plan_length": len(result.output), "rounds": 1,
                "input_tokens": result.input_tokens, "output_tokens": result.output_tokens,
                "cost_usd": result.cost_usd,
                "throttle_count": result.throttle_count, "throttle_seconds": result.throttle_seconds,
                "cache_read_tokens": result.cache_read_tokens,
            })
        logger.info(
            "Plan phase complete: %d input tokens, plan=%d chars",
            result.input_tokens, len(result.output),
        )
        return result.output

    async def _run_act_phase(
        self, task: AgentTask, acc: _ResultAccumulator, exploration_summary: str, plan_text: str,
    ) -> _PhaseResult:
        is_multiphase = bool(task.explore_model or task.plan_model)
        if task.on_event and is_multiphase:
            await task.on_event("phase_started", {"phase": "act", "model": task.model})

        act_system_prompt = self._prompts.build_act_system(task, has_plan=bool(plan_text))
        act_user_prompt = self._prompts.build_act_user(task, exploration_summary, plan_text)
        if task.on_event and act_user_prompt != task.user_prompt:
            await task.on_event("prompt", {"text": act_user_prompt})

        result = await self._call_tool_loop(ToolLoopConfig(
            model=task.model,
            system_prompt=act_system_prompt,
            user_prompt=act_user_prompt,
            tools=make_tools(task.allowed_tools, task.working_directory),
            working_dir=task.working_directory or ".",
            max_rounds=task.max_tool_rounds,
            max_tokens=task.max_tokens,
            on_event=task.on_event,
            on_tool_call=task.on_tool_call,
            nudge_poll=task.nudge_poll,
            phase="act",
        ))
        acc.add(result, task.model)

        if task.on_event and is_multiphase:
            await task.on_event("phase_completed", {
                "phase": "act", "model": task.model,
                "rounds": result.round_count,
                "input_tokens": result.input_tokens, "output_tokens": result.output_tokens,
                "cost_usd": result.cost_usd,
                "throttle_count": result.throttle_count, "throttle_seconds": result.throttle_seconds,
                "cache_read_tokens": result.cache_read_tokens,
            })
        return result

    # ------------------------------------------------------------------
    # Abstract methods — subclasses must override
    # ------------------------------------------------------------------

    async def _call_tool_loop(self, cfg: ToolLoopConfig) -> _PhaseResult:
        """Run the tool-use loop for a single phase. Must be overridden."""
        raise NotImplementedError

    async def _call_plan(
        self, *, model: str, system_prompt: str, user_prompt: str, max_tokens: int,
    ) -> _PhaseResult:
        """Single API call for the plan phase (no tools). Must be overridden."""
        raise NotImplementedError

    async def _compact(
        self,
        messages: list[dict[str, Any]],
        *,
        phase: str,
        on_event: OnAgentEvent | None = None,
    ) -> list[dict[str, Any]]:
        """Compact messages to reduce context size. Default: no-op."""
        return messages
