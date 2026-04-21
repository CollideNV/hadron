"""OpenAI agent backend — tool-use loop using the OpenAI SDK."""

from __future__ import annotations

import json
import os
import time
from typing import Any

import structlog

from hadron.agent.base import OnAgentEvent
from hadron.agent.base_backend import BaseAgentBackend
from hadron.agent.cost import _compute_model_cost
from hadron.agent.messages import _serialize_messages
from hadron.agent.rate_limiter import call_with_retry
from hadron.agent.tool_loop import ToolLoopConfig, _PhaseResult
from hadron.agent.tools import execute_tool, make_tools_openai
from hadron.config.limits import (
    COMPACT_INPUT_TOKEN_THRESHOLD,
    MAX_TOOL_RESULT_CALLBACK_CHARS,
    MAX_TOOL_RESULT_EVENT_CHARS,
)

logger = structlog.stdlib.get_logger(__name__)

_DEFAULT_OPENAI_MODEL = "gpt-4.1"


def _get_openai_transient_errors() -> tuple[type[Exception], ...]:
    """Return OpenAI transient error types (lazy import)."""
    try:
        import openai
        return (openai.RateLimitError, openai.InternalServerError)
    except ImportError:
        return ()


class OpenAIAgentBackend(BaseAgentBackend):
    """Agent backend using the OpenAI Chat Completions API with tool-use loop."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        super().__init__()
        try:
            import openai
        except ImportError:
            raise ImportError(
                "Install openai to use the OpenAI backend: pip install hadron[openai]"
            ) from None
        self._client = openai.AsyncOpenAI(
            api_key=api_key or os.environ.get("HADRON_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY", ""),
            base_url=base_url,
        )
        self._transient_errors = _get_openai_transient_errors()

    async def _call_tool_loop(self, cfg: ToolLoopConfig) -> _PhaseResult:
        """Run the OpenAI tool-use loop for a single phase."""
        tools = make_tools_openai(
            cfg.tools and [t["name"] for t in cfg.tools] or [],
            cfg.working_dir,
        )
        # Build tools list from the names in the Anthropic-format tools passed in cfg
        # cfg.tools is already in Anthropic format — extract names
        tool_names = [t["name"] for t in cfg.tools] if cfg.tools else []
        tools = make_tools_openai(tool_names, cfg.working_dir)

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": cfg.system_prompt},
            {"role": "user", "content": cfg.user_prompt},
        ]

        total_input = 0
        total_output = 0
        all_tool_calls: list[dict[str, Any]] = []
        final_text = ""
        round_num = 0
        total_throttle_count = 0
        total_throttle_seconds = 0.0

        for round_num in range(cfg.max_rounds):
            async def _on_retry(wait: int) -> None:
                if cfg.on_event:
                    await cfg.on_event("output", {
                        "text": f"[Rate limited ({cfg.phase}) — waiting {wait}s before retrying...]",
                        "round": round_num,
                    })

            t0 = time.monotonic()
            retry_result = await call_with_retry(
                lambda: self._client.chat.completions.create(
                    model=cfg.model,
                    max_tokens=cfg.max_tokens,
                    messages=messages,
                    tools=tools or None,
                ),
                label=cfg.phase,
                on_retry=_on_retry,
                transient_errors=self._transient_errors,
            )
            response = retry_result.value
            elapsed = time.monotonic() - t0
            total_throttle_count += retry_result.throttle_count
            total_throttle_seconds += retry_result.throttle_seconds

            usage = response.usage
            input_t = usage.prompt_tokens if usage else 0
            output_t = usage.completion_tokens if usage else 0
            if usage:
                total_input += input_t
                total_output += output_t
            logger.info(
                "llm_response",
                phase=cfg.phase,
                model=cfg.model,
                round=round_num,
                input_tokens=input_t,
                output_tokens=output_t,
                elapsed_s=round(elapsed, 2),
            )

            choice = response.choices[0]
            msg = choice.message

            if msg.content:
                final_text = msg.content
                if cfg.on_event:
                    await cfg.on_event("output", {"text": final_text, "round": round_num})

            # If no tool calls, we're done
            if not msg.tool_calls or choice.finish_reason == "stop":
                break

            # Append assistant message with tool calls
            messages.append(msg.model_dump())

            for tc in msg.tool_calls:
                tool_name = tc.function.name
                try:
                    tool_input = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    tool_input = {"raw": tc.function.arguments}

                logger.info("tool_call", phase=cfg.phase, tool=tool_name, input_preview=json.dumps(tool_input)[:200])
                all_tool_calls.append({"name": tool_name, "input": tool_input})

                if cfg.on_event:
                    await cfg.on_event("tool_call", {
                        "tool": tool_name, "input": tool_input, "round": round_num,
                    })

                result_text = await execute_tool(tool_name, tool_input, cfg.working_dir)

                if cfg.on_event:
                    await cfg.on_event("tool_result", {
                        "tool": tool_name, "result": result_text[:MAX_TOOL_RESULT_EVENT_CHARS], "round": round_num,
                    })

                if cfg.on_tool_call and not cfg.on_event:
                    await cfg.on_tool_call(tool_name, tool_input, result_text[:MAX_TOOL_RESULT_CALLBACK_CHARS])

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_text,
                })

            if choice.finish_reason == "stop":
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
            model=cfg.model,
            input_tokens=total_input,
            output_tokens=total_output,
            cost_usd=cost,
            tool_calls=all_tool_calls,
            conversation=_serialize_openai_messages(messages),
            round_count=round_num + 1 if messages else 0,
            throttle_count=total_throttle_count,
            throttle_seconds=total_throttle_seconds,
        )

    async def _call_plan(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
    ) -> _PhaseResult:
        """Single API call for the plan phase — no tools."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        retry_result = await call_with_retry(
            lambda: self._client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                messages=messages,
            ),
            label="plan",
            transient_errors=self._transient_errors,
        )
        response = retry_result.value
        text = response.choices[0].message.content or ""

        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0
        cost = _compute_model_cost(model, input_tokens, output_tokens)

        return _PhaseResult(
            output=text,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            tool_calls=[],
            conversation=[
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": text},
            ],
            round_count=1,
            throttle_count=retry_result.throttle_count,
            throttle_seconds=retry_result.throttle_seconds,
        )


def _serialize_openai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Serialize OpenAI messages for storage, stripping non-serializable objects."""
    result = []
    for msg in messages:
        if isinstance(msg, dict):
            result.append(msg)
        else:
            # Pydantic model from OpenAI SDK
            try:
                result.append(msg.model_dump())
            except AttributeError:
                result.append({"role": "unknown", "content": str(msg)})
    return result
