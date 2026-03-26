"""Tool-use loop engine — runs the tool-use loop for a single agent phase."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

from hadron.agent.base import ModelStats, OnAgentEvent, OnToolCall
from hadron.agent.compaction import compact_messages, context_reset
from hadron.agent.cost import _compute_model_cost
from hadron.agent.messages import _serialize_messages
from hadron.agent.rate_limiter import call_with_retry
from hadron.agent.tools import execute_tool
from hadron.config.limits import (
    COMPACT_INPUT_TOKEN_THRESHOLD,
    CONTEXT_RESET_TOKEN_THRESHOLD,
    MAX_TOOL_RESULT_CALLBACK_CHARS,
    MAX_TOOL_RESULT_EVENT_CHARS,
)

logger = logging.getLogger(__name__)


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


def parse_response_blocks(response: Any) -> tuple[list[str], list[Any]]:
    """Extract text parts and tool_use blocks from an API response."""
    text_parts = []
    tool_uses = []
    for block in response.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            tool_uses.append(block)
    return text_parts, tool_uses


def cacheable_system(system_prompt: str) -> list[dict[str, Any]]:
    """Wrap system prompt as a content block with cache_control."""
    return [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}]


def cacheable_tools(tools: list[dict]) -> list[dict]:
    """Return tools with cache_control on the last entry."""
    if not tools:
        return tools
    result = [dict(t) for t in tools]
    result[-1] = {**result[-1], "cache_control": {"type": "ephemeral"}}
    return result


async def run_tool_loop(
    client: Any,
    cfg: ToolLoopConfig,
) -> _PhaseResult:
    """Run the tool-use loop for a single phase. Core reusable engine.

    Parameters
    ----------
    client:
        The ``anthropic.AsyncAnthropic`` client instance.
    cfg:
        Loop configuration (model, prompts, tools, etc.).
    """
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

    system = cacheable_system(cfg.system_prompt)
    tools = cacheable_tools(cfg.tools)

    for round_num in range(cfg.max_rounds):
        # API call with rate-limit retry
        async def _on_retry(wait: int) -> None:
            if cfg.on_event:
                await cfg.on_event("output", {
                    "text": f"[Rate limited ({cfg.phase}) — waiting {wait}s before retrying...]",
                    "round": round_num,
                })

        retry_result = await call_with_retry(
            lambda: client.messages.create(
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

        text_parts, tool_uses = parse_response_blocks(response)

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

        # Manage context growth: reset at high threshold, compact at lower
        if response.usage.input_tokens >= CONTEXT_RESET_TOKEN_THRESHOLD and len(messages) >= 3:
            messages = await context_reset(
                client, messages,
                original_task=cfg.user_prompt,
                phase=cfg.phase,
                on_event=cfg.on_event,
            )
        elif response.usage.input_tokens >= COMPACT_INPUT_TOKEN_THRESHOLD and len(messages) >= 5:
            messages = await compact_messages(
                client, messages, phase=cfg.phase, on_event=cfg.on_event,
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
