"""Claude agent backend — tool-use loop using the Anthropic SDK directly."""

from __future__ import annotations

import logging
import os
from typing import Any, AsyncIterator

import anthropic

from hadron.agent.base import AgentEvent, AgentResult, AgentTask, ModelStats, OnAgentEvent
from hadron.agent.compaction import compact_messages
from hadron.agent.cost import _compute_model_cost
from hadron.agent.phases import PhasePromptBuilder
from hadron.agent.rate_limiter import call_with_retry
from hadron.agent.tool_loop import (
    ToolLoopConfig,
    _PhaseResult,
    cacheable_system,
    cacheable_tools,
    parse_response_blocks,
    run_tool_loop,
)
from hadron.agent.tools import execute_tool, make_tools
from hadron.config.limits import (
    MAX_TOOL_RESULT_CALLBACK_CHARS,
)

# Re-export for backwards compatibility (tests import these directly from claude.py)
from hadron.agent.cost import _MODEL_COSTS, _DEFAULT_COST, register_model_cost  # noqa: F401

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


class ClaudeAgentBackend:
    """Agent backend using the Anthropic Messages API with a tool-use loop.

    Supports three-phase execution: Explore (read-only) -> Plan (single call) -> Act (full tools).
    Phases are controlled by task.explore_model and task.plan_model — empty string skips the phase.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key or os.environ.get("HADRON_ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", ""),
        )
        self._prompts = PhasePromptBuilder()

    async def execute(self, task: AgentTask) -> AgentResult:
        """Run the agent's tool-use loop to completion.

        If explore_model and/or plan_model are set, runs a three-phase pipeline:
        1. Explore (Haiku): read-only tool loop to gather codebase context
        2. Plan (Opus): single API call to produce an implementation plan
        3. Act (Sonnet): full tool loop to execute the plan

        If neither is set, falls back to the original single-phase behaviour.
        """
        acc = _ResultAccumulator()

        # Emit the task prompt so the frontend can display it
        if task.on_event:
            await task.on_event("prompt", {"text": task.user_prompt})

        exploration_summary = await self._run_explore_phase(task, acc) if task.explore_model else ""
        plan_text = await self._run_plan_phase(task, acc, exploration_summary) if task.plan_model else ""
        act_result = await self._run_act_phase(task, acc, exploration_summary, plan_text)

        return acc.to_result(act_result.output, task.model)

    async def _run_explore_phase(self, task: AgentTask, acc: _ResultAccumulator) -> str:
        """Phase 1: Read-only tool loop to gather codebase context (typically Haiku)."""
        if task.on_event:
            await task.on_event("phase_started", {"phase": "explore", "model": task.explore_model})

        result = await self._run_tool_loop(ToolLoopConfig(
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
        """Phase 2: Single API call to produce an implementation plan (typically Opus)."""
        if task.on_event:
            await task.on_event("phase_started", {"phase": "plan", "model": task.plan_model})

        result = await self._run_plan_call(
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
        """Phase 3: Full tool loop to execute the plan (typically Sonnet)."""
        is_multiphase = bool(task.explore_model or task.plan_model)
        if task.on_event and is_multiphase:
            await task.on_event("phase_started", {"phase": "act", "model": task.model})

        act_user_prompt = self._prompts.build_act_user(task, exploration_summary, plan_text)
        if task.on_event and act_user_prompt != task.user_prompt:
            await task.on_event("prompt", {"text": act_user_prompt})

        result = await self._run_tool_loop(ToolLoopConfig(
            model=task.model,
            system_prompt=task.system_prompt,
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
    # Delegation to extracted modules
    # ------------------------------------------------------------------

    async def _run_tool_loop(self, cfg: ToolLoopConfig) -> _PhaseResult:
        """Delegate to the extracted tool loop engine."""
        return await run_tool_loop(self._client, cfg)

    async def _compact_messages(
        self,
        messages: list[dict[str, Any]],
        *,
        phase: str,
        on_event: OnAgentEvent | None = None,
    ) -> list[dict[str, Any]]:
        """Delegate to the extracted compaction module."""
        return await compact_messages(self._client, messages, phase=phase, on_event=on_event)

    async def _run_plan_call(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
    ) -> _PhaseResult:
        """Single streaming API call for the plan phase — no tools.

        Uses streaming because the Anthropic SDK requires it for calls
        that may exceed 10 minutes (e.g. Opus with large context).
        """
        system = cacheable_system(system_prompt)

        async def _plan_api_call() -> Any:
            async with self._client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user_prompt}],
            ) as stream:
                async for event in stream:
                    pass
                return await stream.get_final_message()

        retry_result = await call_with_retry(_plan_api_call, label="plan")
        response = retry_result.value

        text_parts, _ = parse_response_blocks(response)
        text = "".join(text_parts)

        cache_creation = getattr(response.usage, "cache_creation_input_tokens", 0) or 0
        cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0

        cost = _compute_model_cost(
            model, response.usage.input_tokens, response.usage.output_tokens,
            cache_creation_tokens=cache_creation, cache_read_tokens=cache_read,
        )

        return _PhaseResult(
            output=text,
            model=model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cost_usd=cost,
            tool_calls=[],
            conversation=[
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": text},
            ],
            round_count=1,
            throttle_count=retry_result.throttle_count,
            throttle_seconds=retry_result.throttle_seconds,
            cache_creation_tokens=cache_creation,
            cache_read_tokens=cache_read,
        )

    # ------------------------------------------------------------------
    # Streaming (unchanged — does not use three-phase yet)
    # ------------------------------------------------------------------

    async def stream(self, task: AgentTask) -> AsyncIterator[AgentEvent]:
        """Stream agent events. Yields events as they happen."""
        tools = cacheable_tools(make_tools(task.allowed_tools, task.working_directory))
        system = cacheable_system(task.system_prompt)
        messages: list[dict[str, Any]] = [{"role": "user", "content": task.user_prompt}]

        for round_num in range(task.max_tool_rounds):
            retry_events: list[AgentEvent] = []

            async def _on_stream_retry(wait: int) -> None:
                retry_events.append(AgentEvent(
                    event_type="text_delta",
                    data={"text": f"[Rate limited — waiting {wait}s before retrying...]"},
                ))

            retry_result = await call_with_retry(
                lambda: self._client.messages.create(
                    model=task.model,
                    max_tokens=task.max_tokens,
                    system=system,
                    tools=tools,
                    messages=messages,
                ),
                label="stream",
                on_retry=_on_stream_retry,
            )
            response = retry_result.value
            for ev in retry_events:
                yield ev

            text_parts, tool_uses = parse_response_blocks(response)
            for text in text_parts:
                yield AgentEvent(event_type="text_delta", data={"text": text})
            for tu in tool_uses:
                yield AgentEvent(
                    event_type="tool_use",
                    data={"name": tu.name, "input": tu.input},
                )

            if not tool_uses or response.stop_reason == "end_turn":
                break

            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for tu in tool_uses:
                result_text = await execute_tool(
                    tu.name, tu.input, task.working_directory or "."
                )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": result_text,
                })
                yield AgentEvent(
                    event_type="tool_result",
                    data={"name": tu.name, "result": result_text[:MAX_TOOL_RESULT_CALLBACK_CHARS]},
                )
            messages.append({"role": "user", "content": tool_results})

            if response.stop_reason == "end_turn":
                break

        yield AgentEvent(event_type="done", data={})
