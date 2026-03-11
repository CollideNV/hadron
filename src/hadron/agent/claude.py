"""Claude agent backend — tool-use loop using the Anthropic SDK directly."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable

import anthropic

from hadron.agent.base import AgentEvent, AgentResult, AgentTask, OnAgentEvent, OnToolCall
from hadron.agent.phases import PhasePromptBuilder
from hadron.agent.rate_limiter import call_with_retry
from hadron.agent.tools import execute_tool, make_tools
from hadron.config.limits import MAX_TOOL_RESULT_CALLBACK_CHARS, MAX_TOOL_RESULT_EVENT_CHARS

logger = logging.getLogger(__name__)

# Per-model cost per million tokens: (input, output)
_MODEL_COSTS: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5-20251001": (0.80, 4.00),
    "claude-sonnet-4-20250514": (3.00, 15.00),
    "claude-opus-4-20250514": (15.00, 75.00),
}
# Fallback for unknown models (use Sonnet pricing)
_DEFAULT_COST = (3.00, 15.00)


def _compute_model_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Compute USD cost for a given model and token counts."""
    cost_in, cost_out = _MODEL_COSTS.get(model, _DEFAULT_COST)
    return (input_tokens * cost_in + output_tokens * cost_out) / 1_000_000


def _serialize_messages(msgs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert messages to JSON-serializable format."""
    result = []
    for msg in msgs:
        entry: dict[str, Any] = {"role": msg["role"]}
        content = msg.get("content")
        if isinstance(content, str):
            entry["content"] = content
        elif isinstance(content, list):
            serialized = []
            for item in content:
                if isinstance(item, dict):
                    serialized.append(item)
                elif hasattr(item, "type"):
                    if item.type == "text":
                        serialized.append({"type": "text", "text": item.text})
                    elif item.type == "tool_use":
                        serialized.append({
                            "type": "tool_use", "id": item.id,
                            "name": item.name, "input": item.input,
                        })
                else:
                    serialized.append(str(item))
            entry["content"] = serialized
        else:
            entry["content"] = str(content) if content else ""
        result.append(entry)
    return result


@dataclass
class ToolLoopConfig:
    """Configuration for a single tool-use loop invocation."""

    model: str
    system_prompt: str
    user_prompt: str
    tools: list[dict]
    working_dir: str
    max_rounds: int
    max_tokens: int
    on_event: OnAgentEvent | None = None
    on_tool_call: OnToolCall | None = None
    nudge_poll: Callable[[], Any] | None = None
    phase: str = ""


@dataclass
class _PhaseResult:
    """Internal result from a single phase."""

    output: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    tool_calls: list[dict[str, Any]]
    conversation: list[dict[str, Any]]
    round_count: int


class ClaudeAgentBackend:
    """Agent backend using the Anthropic Messages API with a tool-use loop.

    Supports three-phase execution: Explore (read-only) -> Plan (single call) -> Act (full tools).
    Phases are controlled by task.explore_model and task.plan_model — empty string skips the phase.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY", ""),
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
        total_input = 0
        total_output = 0
        total_cost = 0.0
        all_tool_calls: list[dict[str, Any]] = []
        all_conversations: list[dict[str, Any]] = []
        total_rounds = 0
        exploration_summary = ""
        plan_text = ""

        # --- PHASE 1: Explore (read-only tools, typically Haiku) ---
        if task.explore_model:
            if task.on_event:
                await task.on_event("phase_started", {
                    "phase": "explore", "model": task.explore_model,
                })

            explore_result = await self._run_tool_loop(ToolLoopConfig(
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
            exploration_summary = explore_result.output
            total_input += explore_result.input_tokens
            total_output += explore_result.output_tokens
            total_cost += explore_result.cost_usd
            all_tool_calls.extend(explore_result.tool_calls)
            all_conversations.extend(explore_result.conversation)
            total_rounds += explore_result.round_count

            if task.on_event:
                await task.on_event("phase_completed", {
                    "phase": "explore",
                    "model": task.explore_model,
                    "summary_length": len(exploration_summary),
                    "rounds": explore_result.round_count,
                    "input_tokens": explore_result.input_tokens,
                    "output_tokens": explore_result.output_tokens,
                })

            logger.info(
                "Explore phase complete: %d rounds, %d input tokens, summary=%d chars",
                explore_result.round_count, explore_result.input_tokens,
                len(exploration_summary),
            )

        # --- PHASE 2: Plan (single call, no tools, typically Opus) ---
        if task.plan_model:
            if task.on_event:
                await task.on_event("phase_started", {
                    "phase": "plan", "model": task.plan_model,
                })

            plan_result = await self._run_plan_call(
                model=task.plan_model,
                system_prompt=self._prompts.build_plan_system(task),
                user_prompt=self._prompts.build_plan_user(task, exploration_summary),
                max_tokens=task.max_tokens,
            )
            plan_text = plan_result.output
            total_input += plan_result.input_tokens
            total_output += plan_result.output_tokens
            total_cost += plan_result.cost_usd
            all_conversations.extend(plan_result.conversation)

            if task.on_event:
                await task.on_event("phase_completed", {
                    "phase": "plan",
                    "model": task.plan_model,
                    "plan_length": len(plan_text),
                    "input_tokens": plan_result.input_tokens,
                    "output_tokens": plan_result.output_tokens,
                })

            logger.info(
                "Plan phase complete: %d input tokens, plan=%d chars",
                plan_result.input_tokens, len(plan_text),
            )

        # --- PHASE 3: Act (full tools, typically Sonnet) ---
        if task.on_event and (task.explore_model or task.plan_model):
            await task.on_event("phase_started", {
                "phase": "act", "model": task.model,
            })

        act_user_prompt = self._prompts.build_act_user(task, exploration_summary, plan_text)
        act_result = await self._run_tool_loop(ToolLoopConfig(
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
        total_input += act_result.input_tokens
        total_output += act_result.output_tokens
        total_cost += act_result.cost_usd
        all_tool_calls.extend(act_result.tool_calls)
        all_conversations.extend(act_result.conversation)
        total_rounds += act_result.round_count

        if task.on_event and (task.explore_model or task.plan_model):
            await task.on_event("phase_completed", {
                "phase": "act",
                "model": task.model,
                "rounds": act_result.round_count,
                "input_tokens": act_result.input_tokens,
                "output_tokens": act_result.output_tokens,
            })

        return AgentResult(
            output=act_result.output,
            input_tokens=total_input,
            output_tokens=total_output,
            cost_usd=total_cost,
            tool_calls=all_tool_calls,
            conversation=all_conversations,
            round_count=total_rounds,
        )

    # ------------------------------------------------------------------
    # Core API call helpers
    # ------------------------------------------------------------------

    async def _run_tool_loop(self, cfg: ToolLoopConfig) -> _PhaseResult:
        """Run the tool-use loop for a single phase. Core reusable engine."""
        messages: list[dict[str, Any]] = [{"role": "user", "content": cfg.user_prompt}]
        total_input = 0
        total_output = 0
        all_tool_calls: list[dict[str, Any]] = []
        final_text = ""
        round_num = 0

        for round_num in range(cfg.max_rounds):
            # API call with rate-limit retry
            async def _on_retry(wait: int) -> None:
                if cfg.on_event:
                    await cfg.on_event("output", {
                        "text": f"[Rate limited ({cfg.phase}) — waiting {wait}s before retrying...]",
                        "round": round_num,
                    })

            response = await call_with_retry(
                lambda: self._client.messages.create(
                    model=cfg.model,
                    max_tokens=cfg.max_tokens,
                    system=cfg.system_prompt,
                    tools=cfg.tools,
                    messages=messages,
                ),
                label=cfg.phase,
                on_retry=_on_retry,
            )

            total_input += response.usage.input_tokens
            total_output += response.usage.output_tokens

            # Collect text and tool use blocks
            text_parts = []
            tool_uses = []
            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "tool_use":
                    tool_uses.append(block)

            if text_parts:
                final_text = "\n".join(text_parts)
                if cfg.on_event:
                    await cfg.on_event("output", {"text": final_text, "round": round_num})

            # If no tool calls, we're done
            if not tool_uses or response.stop_reason == "end_turn":
                break

            # Execute tools and build the response
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for tu in tool_uses:
                logger.info("[%s] Tool call: %s(%s)", cfg.phase, tu.name, json.dumps(tu.input)[:200])
                all_tool_calls.append({"name": tu.name, "input": tu.input})

                if cfg.on_event:
                    await cfg.on_event("tool_call", {
                        "tool": tu.name, "input": tu.input, "round": round_num,
                    })

                result_text = await execute_tool(tu.name, tu.input, cfg.working_dir)

                if cfg.on_event:
                    await cfg.on_event("tool_result", {
                        "tool": tu.name, "result": result_text[:MAX_TOOL_RESULT_EVENT_CHARS], "round": round_num,
                    })

                if cfg.on_tool_call and not cfg.on_event:
                    await cfg.on_tool_call(tu.name, tu.input, result_text[:MAX_TOOL_RESULT_CALLBACK_CHARS])

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": result_text,
                })

            messages.append({"role": "user", "content": tool_results})

            if response.stop_reason == "end_turn":
                break

            # Check for nudge between rounds
            if cfg.nudge_poll:
                nudge = await cfg.nudge_poll()
                if nudge:
                    if cfg.on_event:
                        await cfg.on_event("nudge", {"text": nudge})
                    messages.append({"role": "user", "content": nudge})

        cost = _compute_model_cost(cfg.model, total_input, total_output)

        return _PhaseResult(
            output=final_text,
            input_tokens=total_input,
            output_tokens=total_output,
            cost_usd=cost,
            tool_calls=all_tool_calls,
            conversation=_serialize_messages(messages),
            round_count=round_num + 1 if messages else 0,
        )

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
        async def _plan_api_call() -> Any:
            async with self._client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            ) as stream:
                async for event in stream:
                    pass
                return await stream.get_final_message()

        response = await call_with_retry(_plan_api_call, label="plan")

        text = ""
        for block in response.content:
            if block.type == "text":
                text += block.text

        cost = _compute_model_cost(model, response.usage.input_tokens, response.usage.output_tokens)

        return _PhaseResult(
            output=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cost_usd=cost,
            tool_calls=[],
            conversation=[
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": text},
            ],
            round_count=1,
        )

    # ------------------------------------------------------------------
    # Streaming (unchanged — does not use three-phase yet)
    # ------------------------------------------------------------------

    async def stream(self, task: AgentTask) -> AsyncIterator[AgentEvent]:
        """Stream agent events. Yields events as they happen."""
        tools = make_tools(task.allowed_tools, task.working_directory)
        messages: list[dict[str, Any]] = [{"role": "user", "content": task.user_prompt}]

        for round_num in range(task.max_tool_rounds):
            retry_events: list[AgentEvent] = []

            async def _on_stream_retry(wait: int) -> None:
                retry_events.append(AgentEvent(
                    event_type="text_delta",
                    data={"text": f"[Rate limited — waiting {wait}s before retrying...]"},
                ))

            response = await call_with_retry(
                lambda: self._client.messages.create(
                    model=task.model,
                    max_tokens=task.max_tokens,
                    system=task.system_prompt,
                    tools=tools,
                    messages=messages,
                ),
                label="stream",
                on_retry=_on_stream_retry,
            )
            for ev in retry_events:
                yield ev

            text_parts = []
            tool_uses = []
            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
                    yield AgentEvent(event_type="text_delta", data={"text": block.text})
                elif block.type == "tool_use":
                    tool_uses.append(block)
                    yield AgentEvent(
                        event_type="tool_use",
                        data={"name": block.name, "input": block.input},
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
