"""Claude agent backend — tool-use loop using the Anthropic SDK directly."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable

import anthropic

from hadron.agent.base import AgentEvent, AgentResult, AgentTask, ModelStats, OnAgentEvent, OnToolCall
from hadron.agent.phases import PhasePromptBuilder
from hadron.agent.rate_limiter import call_with_retry
from hadron.agent.tools import execute_tool, make_tools
from hadron.config.limits import (
    COMPACT_INPUT_TOKEN_THRESHOLD,
    MAX_TOOL_RESULT_CALLBACK_CHARS,
    MAX_TOOL_RESULT_EVENT_CHARS,
)

logger = logging.getLogger(__name__)

# Per-model cost per million tokens: (input, output).
# Use register_model_cost() to add entries at runtime without modifying source.
_MODEL_COSTS: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5-20251001": (0.80, 4.00),
    "claude-sonnet-4-20250514": (3.00, 15.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-20250514": (15.00, 75.00),
    "claude-opus-4-6": (15.00, 75.00),
}
# Fallback for unknown models (use Sonnet pricing)
_DEFAULT_COST = (3.00, 15.00)


def register_model_cost(model: str, input_cost: float, output_cost: float) -> None:
    """Register per-million-token costs for a model.

    Allows adding new models at startup (e.g. from database config)
    without modifying source code.
    """
    _MODEL_COSTS[model] = (input_cost, output_cost)


def _compute_model_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """Compute USD cost for a given model and token counts.

    Cache pricing: writes cost 25% more than base input, reads cost 90% less.
    """
    cost_in, cost_out = _MODEL_COSTS.get(model, _DEFAULT_COST)
    cache_write_cost = cost_in * 1.25
    cache_read_cost = cost_in * 0.10
    return (
        input_tokens * cost_in
        + output_tokens * cost_out
        + cache_creation_tokens * cache_write_cost
        + cache_read_tokens * cache_read_cost
    ) / 1_000_000


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
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    tool_calls: list[dict[str, Any]]
    conversation: list[dict[str, Any]]
    round_count: int
    throttle_count: int = 0
    throttle_seconds: float = 0.0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0

    def to_model_stats(self) -> ModelStats:
        return ModelStats(
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            cost_usd=self.cost_usd,
            throttle_count=self.throttle_count,
            throttle_seconds=self.throttle_seconds,
            cache_creation_tokens=self.cache_creation_tokens,
            cache_read_tokens=self.cache_read_tokens,
            api_calls=self.round_count,
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
        total_input = 0
        total_output = 0
        total_cost = 0.0
        all_tool_calls: list[dict[str, Any]] = []
        all_conversations: list[dict[str, Any]] = []
        total_rounds = 0
        total_throttle_count = 0
        total_throttle_seconds = 0.0
        total_cache_creation = 0
        total_cache_read = 0
        breakdown: dict[str, ModelStats] = {}
        exploration_summary = ""
        plan_text = ""

        # Emit the task prompt so the frontend can display it
        if task.on_event:
            await task.on_event("prompt", {"text": task.user_prompt})

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
            total_throttle_count += explore_result.throttle_count
            total_throttle_seconds += explore_result.throttle_seconds
            total_cache_creation += explore_result.cache_creation_tokens
            total_cache_read += explore_result.cache_read_tokens
            stats = explore_result.to_model_stats()
            breakdown[task.explore_model] = breakdown.get(task.explore_model, ModelStats()).merge(stats)

            if task.on_event:
                await task.on_event("phase_completed", {
                    "phase": "explore",
                    "model": task.explore_model,
                    "summary_length": len(exploration_summary),
                    "rounds": explore_result.round_count,
                    "input_tokens": explore_result.input_tokens,
                    "output_tokens": explore_result.output_tokens,
                    "cost_usd": explore_result.cost_usd,
                    "throttle_count": explore_result.throttle_count,
                    "throttle_seconds": explore_result.throttle_seconds,
                    "cache_read_tokens": explore_result.cache_read_tokens,
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
            total_throttle_count += plan_result.throttle_count
            total_throttle_seconds += plan_result.throttle_seconds
            total_cache_creation += plan_result.cache_creation_tokens
            total_cache_read += plan_result.cache_read_tokens
            stats = plan_result.to_model_stats()
            breakdown[task.plan_model] = breakdown.get(task.plan_model, ModelStats()).merge(stats)

            # Emit the plan output so the frontend can display it
            if task.on_event and plan_text:
                await task.on_event("output", {"text": plan_text, "round": 0})

            if task.on_event:
                await task.on_event("phase_completed", {
                    "phase": "plan",
                    "model": task.plan_model,
                    "plan_length": len(plan_text),
                    "rounds": 1,
                    "input_tokens": plan_result.input_tokens,
                    "output_tokens": plan_result.output_tokens,
                    "cost_usd": plan_result.cost_usd,
                    "throttle_count": plan_result.throttle_count,
                    "throttle_seconds": plan_result.throttle_seconds,
                    "cache_read_tokens": plan_result.cache_read_tokens,
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
        if task.on_event and act_user_prompt != task.user_prompt:
            await task.on_event("prompt", {"text": act_user_prompt})
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
        total_throttle_count += act_result.throttle_count
        total_throttle_seconds += act_result.throttle_seconds
        total_cache_creation += act_result.cache_creation_tokens
        total_cache_read += act_result.cache_read_tokens
        act_stats = act_result.to_model_stats()
        breakdown[task.model] = breakdown.get(task.model, ModelStats()).merge(act_stats)

        if task.on_event and (task.explore_model or task.plan_model):
            await task.on_event("phase_completed", {
                "phase": "act",
                "model": task.model,
                "rounds": act_result.round_count,
                "input_tokens": act_result.input_tokens,
                "output_tokens": act_result.output_tokens,
                "cost_usd": act_result.cost_usd,
                "throttle_count": act_result.throttle_count,
                "throttle_seconds": act_result.throttle_seconds,
                "cache_read_tokens": act_result.cache_read_tokens,
            })

        return AgentResult(
            output=act_result.output,
            input_tokens=total_input,
            output_tokens=total_output,
            cost_usd=total_cost,
            tool_calls=all_tool_calls,
            conversation=all_conversations,
            round_count=total_rounds,
            model=task.model,
            throttle_count=total_throttle_count,
            throttle_seconds=total_throttle_seconds,
            cache_creation_tokens=total_cache_creation,
            cache_read_tokens=total_cache_read,
            model_breakdown={m: s.to_dict() for m, s in breakdown.items()},
        )

    # ------------------------------------------------------------------
    # Core API call helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response_blocks(response: Any) -> tuple[list[str], list[Any]]:
        """Extract text parts and tool_use blocks from an API response."""
        text_parts = []
        tool_uses = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_uses.append(block)
        return text_parts, tool_uses

    @staticmethod
    def _cacheable_system(system_prompt: str) -> list[dict[str, Any]]:
        """Wrap system prompt as a content block with cache_control."""
        return [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}]

    @staticmethod
    def _cacheable_tools(tools: list[dict]) -> list[dict]:
        """Return tools with cache_control on the last entry."""
        if not tools:
            return tools
        result = [dict(t) for t in tools]
        result[-1] = {**result[-1], "cache_control": {"type": "ephemeral"}}
        return result

    async def _compact_messages(
        self,
        messages: list[dict[str, Any]],
        *,
        phase: str,
        on_event: OnAgentEvent | None = None,
    ) -> list[dict[str, Any]]:
        """Summarize conversation history to reduce token count.

        Keeps the first user message (original task) and the last assistant+tool
        exchange intact. Everything in between is summarized by a cheap Haiku call.
        """
        # Need at least: original user + some middle + latest exchange
        if len(messages) < 5:
            return messages

        original_user = messages[0]
        # Keep last 2 messages (assistant response + tool results)
        tail = messages[-2:]
        middle = messages[1:-2]

        # Build a text representation of the middle for summarization
        middle_text_parts: list[str] = []
        for msg in middle:
            role = msg.get("role", "?")
            content = msg.get("content", "")
            if isinstance(content, str):
                middle_text_parts.append(f"[{role}]: {content[:2000]}")
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            middle_text_parts.append(f"[{role}]: {item['text'][:2000]}")
                        elif item.get("type") == "tool_use":
                            middle_text_parts.append(f"[tool_call]: {item.get('name', '?')}({json.dumps(item.get('input', {}))[:200]})")
                        elif item.get("type") == "tool_result":
                            middle_text_parts.append(f"[tool_result]: {str(item.get('content', ''))[:500]}")
                    elif hasattr(item, "type"):
                        if item.type == "text":
                            middle_text_parts.append(f"[{role}]: {item.text[:2000]}")
                        elif item.type == "tool_use":
                            middle_text_parts.append(f"[tool_call]: {item.name}({json.dumps(item.input)[:200]})")

        middle_text = "\n".join(middle_text_parts)

        if on_event:
            await on_event("compaction", {
                "phase": phase,
                "messages_before": len(messages),
                "middle_messages": len(middle),
            })

        logger.info(
            "Compacting conversation [%s]: %d messages → summarizing %d middle messages",
            phase, len(messages), len(middle),
        )

        try:
            summary_response = await self._client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4096,
                system="Summarize the following agent conversation history concisely. "
                       "Preserve: key decisions made, files read/written, commands run and their "
                       "outcomes, current progress, and any errors encountered. "
                       "Drop: verbatim file contents, full command outputs, and redundant details.",
                messages=[{"role": "user", "content": middle_text}],
            )
            summary = summary_response.content[0].text
        except Exception as e:
            logger.warning("Compaction failed [%s], keeping original messages: %s", phase, e)
            return messages

        compacted = [
            original_user,
            {"role": "assistant", "content": f"[Conversation compacted — summary of {len(middle)} prior messages]\n\n{summary}"},
            {"role": "user", "content": "Continue from where you left off."},
            *tail,
        ]

        if on_event:
            await on_event("compaction", {
                "phase": phase,
                "messages_before": len(messages),
                "messages_after": len(compacted),
                "summary_length": len(summary),
            })

        logger.info(
            "Compaction complete [%s]: %d → %d messages, summary=%d chars",
            phase, len(messages), len(compacted), len(summary),
        )
        return compacted

    async def _run_tool_loop(self, cfg: ToolLoopConfig) -> _PhaseResult:
        """Run the tool-use loop for a single phase. Core reusable engine."""
        messages: list[dict[str, Any]] = [{"role": "user", "content": cfg.user_prompt}]
        total_input = 0
        total_output = 0
        total_cache_creation = 0
        total_cache_read = 0
        all_tool_calls: list[dict[str, Any]] = []
        final_text = ""
        round_num = 0
        total_throttle_count = 0
        total_throttle_seconds = 0.0

        system = self._cacheable_system(cfg.system_prompt)
        tools = self._cacheable_tools(cfg.tools)

        for round_num in range(cfg.max_rounds):
            # API call with rate-limit retry
            async def _on_retry(wait: int) -> None:
                if cfg.on_event:
                    await cfg.on_event("output", {
                        "text": f"[Rate limited ({cfg.phase}) — waiting {wait}s before retrying...]",
                        "round": round_num,
                    })

            retry_result = await call_with_retry(
                lambda: self._client.messages.create(
                    model=cfg.model,
                    max_tokens=cfg.max_tokens,
                    system=system,
                    tools=tools,
                    messages=messages,
                ),
                label=cfg.phase,
                on_retry=_on_retry,
            )
            response = retry_result.value
            total_throttle_count += retry_result.throttle_count
            total_throttle_seconds += retry_result.throttle_seconds

            total_input += response.usage.input_tokens
            total_output += response.usage.output_tokens
            total_cache_creation += getattr(response.usage, "cache_creation_input_tokens", 0) or 0
            total_cache_read += getattr(response.usage, "cache_read_input_tokens", 0) or 0

            text_parts, tool_uses = self._parse_response_blocks(response)

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

            # Compact conversation if input tokens are growing too large
            # or we just got rate-limited (which suggests high token throughput)
            should_compact = (
                response.usage.input_tokens >= COMPACT_INPUT_TOKEN_THRESHOLD
                or retry_result.throttle_count > 0
            )
            if should_compact and len(messages) >= 5:
                messages = await self._compact_messages(
                    messages, phase=cfg.phase, on_event=cfg.on_event,
                )

            # Check for nudge between rounds
            if cfg.nudge_poll:
                nudge = await cfg.nudge_poll()
                if nudge:
                    if cfg.on_event:
                        await cfg.on_event("nudge", {"text": nudge})
                    messages.append({"role": "user", "content": nudge})

        cost = _compute_model_cost(
            cfg.model, total_input, total_output,
            cache_creation_tokens=total_cache_creation,
            cache_read_tokens=total_cache_read,
        )

        return _PhaseResult(
            output=final_text,
            model=cfg.model,
            input_tokens=total_input,
            output_tokens=total_output,
            cost_usd=cost,
            tool_calls=all_tool_calls,
            conversation=_serialize_messages(messages),
            round_count=round_num + 1 if messages else 0,
            throttle_count=total_throttle_count,
            throttle_seconds=total_throttle_seconds,
            cache_creation_tokens=total_cache_creation,
            cache_read_tokens=total_cache_read,
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
        system = self._cacheable_system(system_prompt)

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

        text_parts, _ = self._parse_response_blocks(response)
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
        tools = self._cacheable_tools(make_tools(task.allowed_tools, task.working_directory))
        system = self._cacheable_system(task.system_prompt)
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

            text_parts, tool_uses = self._parse_response_blocks(response)
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
