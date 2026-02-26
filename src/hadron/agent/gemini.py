"""Gemini agent backend — tool-use loop using the Google GenAI SDK."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, AsyncIterator

from google import genai
from google.genai import types as genai_types

from hadron.agent.base import AgentEvent, AgentResult, AgentTask
from hadron.agent.tools import TOOL_DEFINITIONS, execute_tool

logger = logging.getLogger(__name__)

from hadron.config.providers import get_model_config

# Default cost if not in config
_DEFAULT_COST = (1.25, 10.00)

# Rate limit retry settings
_RATE_LIMIT_MAX_RETRIES = 5
_RATE_LIMIT_BASE_WAIT = 30  # seconds


def _make_tools(allowed: list[str]) -> list[genai_types.Tool]:
    """Build Gemini-formatted tool declarations."""
    declarations = []
    for name in allowed:
        defn = TOOL_DEFINITIONS.get(name)
        if defn is None:
            continue
        declarations.append(genai_types.FunctionDeclaration(
            name=defn["name"],
            description=defn["description"],
            parameters=defn["parameters"],
        ))
    if not declarations:
        return []
    return [genai_types.Tool(function_declarations=declarations)]


def _cost_for_model(model: str) -> tuple[float, float]:
    """Return (cost_per_M_input, cost_per_M_output) for a model."""
    cfg = get_model_config(model)
    if cfg:
        return (cfg["cost_input_1m"], cfg["cost_output_1m"])
    return _DEFAULT_COST


class GeminiAgentBackend:
    """Agent backend using the Google GenAI SDK with a tool-use loop.

    Flow: send message → if function_call in response → execute tool → send result → repeat.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self._client = genai.Client(api_key=self._api_key)

    @property
    def name(self) -> str:
        return "gemini"

    async def execute(self, task: AgentTask) -> AgentResult:
        """Run the agent's tool-use loop to completion."""
        tools = _make_tools(task.allowed_tools)
        config = genai_types.GenerateContentConfig(
            system_instruction=task.system_prompt,
            tools=tools,
            max_output_tokens=task.max_tokens,
            temperature=0.0,
        )

        contents: list[genai_types.Content] = [
            genai_types.Content(role="user", parts=[genai_types.Part.from_text(text=task.user_prompt)]),
        ]

        total_input = 0
        total_output = 0
        all_tool_calls: list[dict[str, Any]] = []
        final_text = ""
        round_num = -1

        for round_num in range(task.max_tool_rounds):
            # API call with rate-limit retry
            response = await self._call_with_retry(task, config, contents, round_num)

            # Accumulate usage
            if response.usage_metadata:
                total_input += response.usage_metadata.prompt_token_count or 0
                total_output += response.usage_metadata.candidates_token_count or 0

            # Process response parts
            candidate = response.candidates[0] if response.candidates else None
            if candidate is None:
                break

            text_parts: list[str] = []
            function_calls: list[genai_types.FunctionCall] = []

            for part in candidate.content.parts:
                if part.text:
                    text_parts.append(part.text)
                if part.function_call:
                    function_calls.append(part.function_call)

            if text_parts:
                final_text = "\n".join(text_parts)
                if task.on_event:
                    await task.on_event("output", {"text": final_text, "round": round_num})

            # If no function calls, we're done
            if not function_calls:
                break

            # Add the assistant response to contents
            contents.append(candidate.content)

            # Execute function calls
            function_responses: list[genai_types.Part] = []
            for fc in function_calls:
                fc_name = fc.name
                fc_args = dict(fc.args) if fc.args else {}

                logger.info("Tool call: %s(%s)", fc_name, json.dumps(fc_args)[:200])
                all_tool_calls.append({"name": fc_name, "input": fc_args})

                if task.on_event:
                    await task.on_event("tool_call", {
                        "tool": fc_name, "input": fc_args, "round": round_num,
                    })

                result_text = await execute_tool(
                    fc_name, fc_args, task.working_directory or "."
                )

                if task.on_event:
                    await task.on_event("tool_result", {
                        "tool": fc_name, "result": result_text[:10_000], "round": round_num,
                    })

                if task.on_tool_call and not task.on_event:
                    await task.on_tool_call(fc_name, fc_args, result_text[:5000])

                function_responses.append(
                    genai_types.Part.from_function_response(
                        name=fc_name,
                        response={"result": result_text},
                    )
                )

            contents.append(genai_types.Content(role="user", parts=function_responses))

            # Check for nudge between rounds
            if task.nudge_poll:
                nudge = await task.nudge_poll()
                if nudge:
                    if task.on_event:
                        await task.on_event("nudge", {"text": nudge})
                    contents.append(
                        genai_types.Content(role="user", parts=[genai_types.Part.from_text(text=nudge)])
                    )

        cost_input, cost_output = _cost_for_model(task.model)
        cost = (total_input * cost_input + total_output * cost_output) / 1_000_000

        # Serialize contents for conversation storage
        conversation = self._serialize_contents(contents)

        return AgentResult(
            output=final_text,
            input_tokens=total_input,
            output_tokens=total_output,
            cost_usd=cost,
            tool_calls=all_tool_calls,
            conversation=conversation,
            round_count=round_num + 1 if contents else 0,
        )

    async def stream(self, task: AgentTask) -> AsyncIterator[AgentEvent]:
        """Stream agent events. Yields events as they happen."""
        tools = _make_tools(task.allowed_tools)
        config = genai_types.GenerateContentConfig(
            system_instruction=task.system_prompt,
            tools=tools,
            max_output_tokens=task.max_tokens,
            temperature=0.0,
        )

        contents: list[genai_types.Content] = [
            genai_types.Content(role="user", parts=[genai_types.Part.from_text(text=task.user_prompt)]),
        ]

        for round_num in range(task.max_tool_rounds):
            response = await self._call_with_retry(task, config, contents, round_num)

            candidate = response.candidates[0] if response.candidates else None
            if candidate is None:
                break

            text_parts: list[str] = []
            function_calls: list[genai_types.FunctionCall] = []

            for part in candidate.content.parts:
                if part.text:
                    text_parts.append(part.text)
                    yield AgentEvent(event_type="text_delta", data={"text": part.text})
                if part.function_call:
                    function_calls.append(part.function_call)
                    yield AgentEvent(
                        event_type="tool_use",
                        data={"name": part.function_call.name, "input": dict(part.function_call.args) if part.function_call.args else {}},
                    )

            if not function_calls:
                break

            contents.append(candidate.content)

            function_responses: list[genai_types.Part] = []
            for fc in function_calls:
                fc_name = fc.name
                fc_args = dict(fc.args) if fc.args else {}
                result_text = await execute_tool(
                    fc_name, fc_args, task.working_directory or "."
                )
                function_responses.append(
                    genai_types.Part.from_function_response(
                        name=fc_name,
                        response={"result": result_text},
                    )
                )
                yield AgentEvent(
                    event_type="tool_result",
                    data={"name": fc_name, "result": result_text[:5000]},
                )

            contents.append(genai_types.Content(role="user", parts=function_responses))

        yield AgentEvent(event_type="done", data={})

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _call_with_retry(
        self,
        task: AgentTask,
        config: genai_types.GenerateContentConfig,
        contents: list[genai_types.Content],
        round_num: int,
    ) -> genai_types.GenerateContentResponse:
        """Call the Gemini API with exponential-backoff rate-limit handling."""
        for attempt in range(_RATE_LIMIT_MAX_RETRIES):
            try:
                response = await self._client.aio.models.generate_content(
                    model=task.model,
                    contents=contents,
                    config=config,
                )
                return response
            except Exception as e:
                error_str = str(e).lower()
                is_rate_limit = "429" in error_str or "resource exhausted" in error_str or "rate" in error_str
                if not is_rate_limit or attempt == _RATE_LIMIT_MAX_RETRIES - 1:
                    raise
                wait = _RATE_LIMIT_BASE_WAIT * (attempt + 1)
                logger.warning(
                    "Gemini rate limited (attempt %d/%d), waiting %ds: %s",
                    attempt + 1, _RATE_LIMIT_MAX_RETRIES, wait, e,
                )
                if task.on_event:
                    await task.on_event("output", {
                        "text": f"[Rate limited — waiting {wait}s before retrying...]",
                        "round": round_num,
                    })
                await asyncio.sleep(wait)
        # Unreachable, but keeps mypy happy
        raise RuntimeError("Exhausted rate-limit retries")

    @staticmethod
    def _serialize_contents(contents: list[genai_types.Content]) -> list[dict[str, Any]]:
        """Convert Gemini Content objects to JSON-serializable dicts."""
        result: list[dict[str, Any]] = []
        for content in contents:
            entry: dict[str, Any] = {"role": content.role}
            parts: list[dict[str, Any]] = []
            for part in content.parts:
                if part.text:
                    parts.append({"type": "text", "text": part.text})
                elif part.function_call:
                    parts.append({
                        "type": "function_call",
                        "name": part.function_call.name,
                        "args": dict(part.function_call.args) if part.function_call.args else {},
                    })
                elif part.function_response:
                    parts.append({
                        "type": "function_response",
                        "name": part.function_response.name,
                        "response": (
                            dict(part.function_response.response) if part.function_response.response else {}
                        ),
                    })
            entry["parts"] = parts
            result.append(entry)
        return result
