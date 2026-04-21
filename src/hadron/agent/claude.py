"""Claude agent backend — tool-use loop using the Anthropic SDK directly."""

from __future__ import annotations

import os
from typing import Any, AsyncIterator

import anthropic

from hadron.agent.base import AgentEvent, AgentResult, AgentTask, ModelStats, OnAgentEvent
from hadron.agent.base_backend import BaseAgentBackend, _ResultAccumulator
from hadron.agent.compaction import compact_messages
from hadron.agent.cost import _compute_model_cost
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


class ClaudeAgentBackend(BaseAgentBackend):
    """Agent backend using the Anthropic Messages API with a tool-use loop.

    Supports three-phase execution: Explore (read-only) -> Plan (single call) -> Act (full tools).
    Phases are controlled by task.explore_model and task.plan_model — empty string skips the phase.
    """

    def __init__(self, api_key: str | None = None) -> None:
        super().__init__()
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key or os.environ.get("HADRON_ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", ""),
        )

    # ------------------------------------------------------------------
    # Override abstract methods
    # ------------------------------------------------------------------

    async def _call_tool_loop(self, cfg: ToolLoopConfig) -> _PhaseResult:
        """Delegate to the extracted Anthropic tool loop engine."""
        return await run_tool_loop(self._client, cfg)

    async def _call_plan(
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

    async def _compact(
        self,
        messages: list[dict[str, Any]],
        *,
        phase: str,
        on_event: OnAgentEvent | None = None,
    ) -> list[dict[str, Any]]:
        """Delegate to the extracted compaction module (Haiku-based)."""
        return await compact_messages(self._client, messages, phase=phase, on_event=on_event)

    # ------------------------------------------------------------------
    # Keep _compact_messages for backwards compatibility (tests use it)
    # ------------------------------------------------------------------

    async def _compact_messages(
        self,
        messages: list[dict[str, Any]],
        *,
        phase: str,
        on_event: OnAgentEvent | None = None,
    ) -> list[dict[str, Any]]:
        """Delegate to the extracted compaction module."""
        return await compact_messages(self._client, messages, phase=phase, on_event=on_event)

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
