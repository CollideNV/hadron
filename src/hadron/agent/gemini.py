"""Gemini agent backend — tool-use loop using the Google GenAI SDK."""

from __future__ import annotations

import json
import os
import time
from typing import Any

import structlog

from hadron.agent.base import OnAgentEvent
from hadron.agent.base_backend import BaseAgentBackend
from hadron.agent.cost import _compute_model_cost
from hadron.agent.rate_limiter import call_with_retry
from hadron.agent.tool_loop import ToolLoopConfig, _PhaseResult
from hadron.agent.tools import execute_tool, make_tools_gemini
from hadron.config.limits import (
    MAX_TOOL_RESULT_CALLBACK_CHARS,
    MAX_TOOL_RESULT_EVENT_CHARS,
)

logger = structlog.stdlib.get_logger(__name__)

_DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


def _get_gemini_transient_errors() -> tuple[type[Exception], ...]:
    """Return Gemini transient error types (lazy import)."""
    try:
        from google.api_core import exceptions as google_exceptions
        return (
            google_exceptions.ResourceExhausted,
            google_exceptions.ServiceUnavailable,
            google_exceptions.InternalServerError,
        )
    except ImportError:
        return ()


class GeminiAgentBackend(BaseAgentBackend):
    """Agent backend using the Google Gemini API with function-calling loop."""

    def __init__(self, api_key: str | None = None) -> None:
        super().__init__()
        try:
            from google import genai
        except ImportError:
            raise ImportError(
                "Install google-genai to use the Gemini backend: pip install hadron[gemini]"
            ) from None
        # google-genai SDK bug: GOOGLE_GENAI_USE_VERTEXAI env var overrides
        # the vertexai=False constructor kwarg, routing requests to Vertex AI
        # (aiplatform.googleapis.com) which rejects API keys with 401.
        # Temporarily clear it so the explicit kwarg takes effect.
        saved_vertex_env = os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI", None)
        try:
            self._client = genai.Client(
                api_key=api_key or os.environ.get("HADRON_GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY", ""),
                vertexai=False,
            )
        finally:
            if saved_vertex_env is not None:
                os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = saved_vertex_env
        self._transient_errors = _get_gemini_transient_errors()

    async def _call_tool_loop(self, cfg: ToolLoopConfig) -> _PhaseResult:
        """Run the Gemini function-calling loop for a single phase."""
        from google.genai import types

        tool_names = [t["name"] for t in cfg.tools] if cfg.tools else []
        fn_declarations = make_tools_gemini(tool_names, cfg.working_dir)

        tools = [types.Tool(function_declarations=fn_declarations)] if fn_declarations else []

        contents: list[Any] = [
            types.Content(role="user", parts=[types.Part.from_text(text=cfg.user_prompt)])
        ]

        total_input = 0
        total_output = 0
        all_tool_calls: list[dict[str, Any]] = []
        final_text = ""
        round_num = 0
        total_throttle_count = 0
        total_throttle_seconds = 0.0

        config = types.GenerateContentConfig(
            system_instruction=cfg.system_prompt,
            max_output_tokens=cfg.max_tokens,
            tools=tools,
        )

        for round_num in range(cfg.max_rounds):
            async def _on_retry(wait: int) -> None:
                if cfg.on_event:
                    await cfg.on_event("output", {
                        "text": f"[Rate limited ({cfg.phase}) — waiting {wait}s before retrying...]",
                        "round": round_num,
                    })

            t0 = time.monotonic()
            retry_result = await call_with_retry(
                lambda: self._client.aio.models.generate_content(
                    model=cfg.model,
                    contents=contents,
                    config=config,
                ),
                label=cfg.phase,
                on_retry=_on_retry,
                transient_errors=self._transient_errors,
            )
            response = retry_result.value
            elapsed = time.monotonic() - t0
            total_throttle_count += retry_result.throttle_count
            total_throttle_seconds += retry_result.throttle_seconds

            usage = getattr(response, "usage_metadata", None)
            input_t = 0
            output_t = 0
            if usage:
                input_t = getattr(usage, "prompt_token_count", 0) or 0
                output_t = getattr(usage, "candidates_token_count", 0) or 0
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

            # Extract text and function calls from response
            candidate = response.candidates[0] if response.candidates else None
            if not candidate or not candidate.content or not candidate.content.parts:
                break

            text_parts = []
            fn_calls = []
            for part in candidate.content.parts:
                if hasattr(part, "text") and part.text:
                    text_parts.append(part.text)
                if hasattr(part, "function_call") and part.function_call:
                    fn_calls.append(part.function_call)

            if text_parts:
                final_text = "\n".join(text_parts)
                if cfg.on_event:
                    await cfg.on_event("output", {"text": final_text, "round": round_num})

            if not fn_calls:
                break

            # Add model response to contents
            contents.append(candidate.content)

            # Execute each function call
            fn_response_parts = []
            for fc in fn_calls:
                tool_name = fc.name
                tool_input = dict(fc.args) if fc.args else {}

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

                fn_response_parts.append(
                    types.Part.from_function_response(
                        name=tool_name,
                        response={"result": result_text},
                    )
                )

            contents.append(types.Content(role="user", parts=fn_response_parts))

            # Check for nudge between rounds
            if cfg.nudge_poll:
                nudge = await cfg.nudge_poll()
                if nudge:
                    if cfg.on_event:
                        await cfg.on_event("nudge", {"text": nudge})
                    contents.append(
                        types.Content(role="user", parts=[types.Part.from_text(text=nudge)])
                    )

        cost = _compute_model_cost(cfg.model, total_input, total_output)

        return _PhaseResult(
            output=final_text,
            model=cfg.model,
            input_tokens=total_input,
            output_tokens=total_output,
            cost_usd=cost,
            tool_calls=all_tool_calls,
            conversation=[
                {"role": "user", "content": cfg.user_prompt},
                {"role": "assistant", "content": final_text},
            ],
            round_count=round_num + 1 if contents else 0,
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
        """Single Gemini API call for the plan phase — no tools."""
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            max_output_tokens=max_tokens,
        )

        contents = [
            types.Content(role="user", parts=[types.Part.from_text(text=user_prompt)])
        ]

        retry_result = await call_with_retry(
            lambda: self._client.aio.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            ),
            label="plan",
            transient_errors=self._transient_errors,
        )
        response = retry_result.value

        text = ""
        candidate = response.candidates[0] if response.candidates else None
        if candidate and candidate.content and candidate.content.parts:
            text_parts = [p.text for p in candidate.content.parts if hasattr(p, "text") and p.text]
            text = "\n".join(text_parts)

        usage = getattr(response, "usage_metadata", None)
        input_tokens = getattr(usage, "prompt_token_count", 0) or 0 if usage else 0
        output_tokens = getattr(usage, "candidates_token_count", 0) or 0 if usage else 0
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
