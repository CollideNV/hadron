"""Claude agent backend — tool-use loop using the Anthropic SDK directly."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, AsyncIterator

import anthropic

from hadron.agent.base import AgentEvent, AgentResult, AgentTask
from hadron.agent.tools import TOOL_DEFINITIONS, execute_tool

logger = logging.getLogger(__name__)

from hadron.config.providers import get_model_config

# Default cost if not in config
_DEFAULT_COST = (3.00, 15.00)

# Rate limit retry settings
_RATE_LIMIT_MAX_RETRIES = 5
_RATE_LIMIT_BASE_WAIT = 60  # seconds


def _make_tools(allowed: list[str]) -> list[dict]:
    """Build Anthropic-formatted tool definitions for the allowed tool set."""
    tools = []
    for name in allowed:
        defn = TOOL_DEFINITIONS.get(name)
        if defn is None:
            continue
        tools.append({
            "name": defn["name"],
            "description": defn["description"],
            "input_schema": defn["parameters"],
        })
    return tools


def _cost_for_model(model: str) -> tuple[float, float]:
    """Return (cost_per_M_input, cost_per_M_output) for a model."""
    cfg = get_model_config(model)
    if cfg:
        return (cfg["cost_input_1m"], cfg["cost_output_1m"])
    return _DEFAULT_COST


class ClaudeAgentBackend:
    """Agent backend using the Anthropic Messages API with a tool-use loop.

    Flow: send message → if tool_use in response → execute tool → send result → repeat.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY", ""),
        )

    @property
    def name(self) -> str:
        return "anthropic"

    async def _call_with_retry(
        self,
        task: AgentTask,
        tools: list[dict],
        messages: list[dict[str, Any]],
        round_num: int,
    ) -> Any:
        """Call the Anthropic API with exponential-backoff rate-limit handling."""
        for attempt in range(_RATE_LIMIT_MAX_RETRIES):
            try:
                return await self._client.messages.create(
                    model=task.model,
                    max_tokens=task.max_tokens,
                    system=task.system_prompt,
                    tools=tools,
                    messages=messages,
                )
            except anthropic.RateLimitError as e:
                if attempt == _RATE_LIMIT_MAX_RETRIES - 1:
                    raise
                wait = _RATE_LIMIT_BASE_WAIT * (attempt + 1)
                logger.warning(
                    "Rate limited (attempt %d/%d), waiting %ds: %s",
                    attempt + 1, _RATE_LIMIT_MAX_RETRIES, wait, e,
                )
                if task.on_event:
                    await task.on_event("output", {
                        "text": f"[Rate limited — waiting {wait}s before retrying...]",
                        "round": round_num,
                    })
                await asyncio.sleep(wait)
        raise RuntimeError("Exhausted rate-limit retries")  # unreachable

    async def execute(self, task: AgentTask) -> AgentResult:
        """Run the agent's tool-use loop to completion."""
        tools = _make_tools(task.allowed_tools)
        messages: list[dict[str, Any]] = [{"role": "user", "content": task.user_prompt}]

        total_input = 0
        total_output = 0
        all_tool_calls: list[dict[str, Any]] = []
        final_text = ""
        round_num = -1

        for round_num in range(task.max_tool_rounds):
            response = await self._call_with_retry(task, tools, messages, round_num)

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
                # Emit agent text output
                if task.on_event:
                    await task.on_event("output", {"text": final_text, "round": round_num})

            # If no tool calls, we're done
            if not tool_uses or response.stop_reason == "end_turn" and not tool_uses:
                break

            # Execute tools and build the response
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for tu in tool_uses:
                logger.info("Tool call: %s(%s)", tu.name, json.dumps(tu.input)[:200])
                all_tool_calls.append({"name": tu.name, "input": tu.input})

                # Emit full tool call (no truncation)
                if task.on_event:
                    await task.on_event("tool_call", {
                        "tool": tu.name, "input": tu.input, "round": round_num,
                    })

                result_text = await execute_tool(
                    tu.name, tu.input, task.working_directory or "."
                )

                # Emit full tool result (capped at 10k)
                if task.on_event:
                    await task.on_event("tool_result", {
                        "tool": tu.name, "result": result_text[:10_000], "round": round_num,
                    })

                if task.on_tool_call and not task.on_event:
                    await task.on_tool_call(tu.name, tu.input, result_text[:5000])

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": result_text,
                })

            messages.append({"role": "user", "content": tool_results})

            if response.stop_reason == "end_turn":
                break

            # Check for nudge between rounds
            if task.nudge_poll:
                nudge = await task.nudge_poll()
                if nudge:
                    if task.on_event:
                        await task.on_event("nudge", {"text": nudge})
                    messages.append({"role": "user", "content": nudge})

        cost_in, cost_out = _cost_for_model(task.model)
        cost = (total_input * cost_in + total_output * cost_out) / 1_000_000

        # Serialize messages for conversation storage
        def _serialize_messages(msgs: list[dict[str, Any]]) -> list[dict[str, Any]]:
            """Convert messages to JSON-serializable format."""
            result = []
            for msg in msgs:
                entry: dict[str, Any] = {"role": msg["role"]}
                content = msg.get("content")
                if isinstance(content, str):
                    entry["content"] = content
                elif isinstance(content, list):
                    # Could be tool_result blocks or response content blocks
                    serialized = []
                    for item in content:
                        if isinstance(item, dict):
                            serialized.append(item)
                        elif hasattr(item, "type"):
                            # Anthropic content block object
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

        return AgentResult(
            output=final_text,
            input_tokens=total_input,
            output_tokens=total_output,
            cost_usd=cost,
            tool_calls=all_tool_calls,
            conversation=_serialize_messages(messages),
            round_count=round_num + 1 if messages else 0,
        )

    async def stream(self, task: AgentTask) -> AsyncIterator[AgentEvent]:
        """Stream agent events. Yields events as they happen."""
        tools = _make_tools(task.allowed_tools)
        messages: list[dict[str, Any]] = [{"role": "user", "content": task.user_prompt}]

        for round_num in range(task.max_tool_rounds):
            response = await self._call_with_retry(task, tools, messages, round_num)

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

            if not tool_uses or response.stop_reason == "end_turn" and not tool_uses:
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
                    data={"name": tu.name, "result": result_text[:5000]},
                )
            messages.append({"role": "user", "content": tool_results})

            if response.stop_reason == "end_turn":
                break

        yield AgentEvent(event_type="done", data={})
