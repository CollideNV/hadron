"""Gemini agent backend — tool-use loop using the Google GenAI SDK directly."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, TypeVar

from google import genai
from google.genai import types as gtypes

from hadron.agent.base import AgentEvent, AgentResult, AgentTask
from hadron.agent.phases import PhasePromptBuilder
from hadron.agent.tools import execute_tool

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

# Per-model cost per million tokens: (input, output)
# Prices as of March 2026 for under-200k context window (paid tier).
_MODEL_COSTS: dict[str, tuple[float, float]] = {
    # Gemini 2.5 — stable
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    # Gemini 3 — preview
    "gemini-3-flash-preview": (0.50, 3.00),
    "gemini-3.1-pro-preview": (2.00, 12.00),
    "gemini-3.1-flash-lite-preview": (0.25, 1.50),
}
# Fallback for unknown Gemini models (use Flash pricing)
_DEFAULT_COST = (0.30, 2.50)

# Rate limit retry settings
_RATE_LIMIT_MAX_RETRIES = 5
_RATE_LIMIT_BASE_WAIT = 60  # seconds

# Truncation limits for tool result events and callbacks
_MAX_TOOL_RESULT_EVENT_CHARS = 10_000
_MAX_TOOL_RESULT_CALLBACK_CHARS = 5_000


def _compute_model_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Compute USD cost for a given Gemini model and token counts."""
    cost_in, cost_out = _MODEL_COSTS.get(model, _DEFAULT_COST)
    return (input_tokens * cost_in + output_tokens * cost_out) / 1_000_000


# ------------------------------------------------------------------
# Tool definition translation (Anthropic format → Gemini format)
# ------------------------------------------------------------------

def _make_gemini_tools(allowed: list[str], working_dir: str | None) -> list[gtypes.Tool]:
    """Build Gemini FunctionDeclaration tools from the allowed tool names.

    Translates the Anthropic-style JSON Schema tool definitions into
    Gemini's FunctionDeclaration format.
    """
    from hadron.agent.tools import _ALL_TOOL_DEFS

    declarations: list[gtypes.FunctionDeclaration] = []
    for name in allowed:
        if name not in _ALL_TOOL_DEFS:
            continue
        defn = _ALL_TOOL_DEFS[name]
        schema = defn["input_schema"]

        properties = {}
        for prop_name, prop_schema in schema.get("properties", {}).items():
            properties[prop_name] = gtypes.Schema(
                type=prop_schema["type"].upper(),
                description=prop_schema.get("description", ""),
            )

        declarations.append(gtypes.FunctionDeclaration(
            name=defn["name"],
            description=defn["description"],
            parameters=gtypes.Schema(
                type="OBJECT",
                properties=properties,
                required=schema.get("required", []),
            ),
        ))

    if not declarations:
        return []
    return [gtypes.Tool(function_declarations=declarations)]


def _serialize_messages(msgs: list[gtypes.Content]) -> list[dict[str, Any]]:
    """Convert Gemini Content objects to JSON-serializable format."""
    result = []
    for msg in msgs:
        entry: dict[str, Any] = {"role": msg.role}
        parts_out = []
        if msg.parts:
            for part in msg.parts:
                if part.text:
                    parts_out.append({"type": "text", "text": part.text})
                elif part.function_call:
                    parts_out.append({
                        "type": "function_call",
                        "name": part.function_call.name,
                        "args": dict(part.function_call.args) if part.function_call.args else {},
                    })
                elif part.function_response:
                    parts_out.append({
                        "type": "function_response",
                        "name": part.function_response.name,
                    })
        entry["content"] = parts_out
        result.append(entry)
    return result


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


class GeminiAgentBackend:
    """Agent backend using the Google GenAI API with a tool-use loop.

    Supports three-phase execution: Explore (read-only) -> Plan (single call) -> Act (full tools).
    Phases are controlled by task.explore_model and task.plan_model — empty string skips the phase.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._client = genai.Client(
            api_key=api_key or os.environ.get("GOOGLE_API_KEY", ""),
        )
        self._prompts = PhasePromptBuilder()

    async def _call_with_retry(
        self,
        api_call: Callable[[], Any],
        label: str,
        on_retry: Callable[[int], Any] | None = None,
    ) -> _T:
        """Call *api_call* with exponential back-off on rate-limit errors."""
        for attempt in range(_RATE_LIMIT_MAX_RETRIES):
            try:
                return await api_call()
            except Exception as e:
                # Google GenAI raises google.genai.errors.ClientError with status 429
                is_rate_limit = (
                    "429" in str(e)
                    or "RESOURCE_EXHAUSTED" in str(e)
                    or "rate" in str(e).lower()
                )
                if not is_rate_limit or attempt == _RATE_LIMIT_MAX_RETRIES - 1:
                    raise
                wait = _RATE_LIMIT_BASE_WAIT * (attempt + 1)
                logger.warning(
                    "Rate limited [%s] (attempt %d/%d), waiting %ds: %s",
                    label, attempt + 1, _RATE_LIMIT_MAX_RETRIES, wait, e,
                )
                if on_retry:
                    await on_retry(wait)
                await asyncio.sleep(wait)
        raise AssertionError("unreachable")  # pragma: no cover

    async def execute(self, task: AgentTask) -> AgentResult:
        """Run the agent's tool-use loop to completion.

        Supports three-phase execution identical to ClaudeAgentBackend:
        1. Explore (read-only tools, typically Flash)
        2. Plan (single API call, no tools, typically Pro)
        3. Act (full tools, default model)
        """
        total_input = 0
        total_output = 0
        total_cost = 0.0
        all_tool_calls: list[dict[str, Any]] = []
        all_conversations: list[dict[str, Any]] = []
        total_rounds = 0
        exploration_summary = ""
        plan_text = ""

        # --- PHASE 1: Explore ---
        if task.explore_model:
            if task.on_event:
                await task.on_event("phase_started", {
                    "phase": "explore", "model": task.explore_model,
                })

            explore_result = await self._run_tool_loop(
                model=task.explore_model,
                system_prompt=self._prompts.build_explore_system(task),
                user_prompt=task.user_prompt,
                tools=_make_gemini_tools(task.explore_tools, task.working_directory),
                working_dir=task.working_directory or ".",
                max_rounds=task.explore_max_rounds,
                max_tokens=task.max_tokens,
                on_event=task.on_event,
                phase="explore",
            )
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

        # --- PHASE 2: Plan ---
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

        # --- PHASE 3: Act ---
        if task.on_event and (task.explore_model or task.plan_model):
            await task.on_event("phase_started", {
                "phase": "act", "model": task.model,
            })

        act_user_prompt = self._prompts.build_act_user(task, exploration_summary, plan_text)
        act_result = await self._run_tool_loop(
            model=task.model,
            system_prompt=task.system_prompt,
            user_prompt=act_user_prompt,
            tools=_make_gemini_tools(task.allowed_tools, task.working_directory),
            working_dir=task.working_directory or ".",
            max_rounds=task.max_tool_rounds,
            max_tokens=task.max_tokens,
            on_event=task.on_event,
            on_tool_call=task.on_tool_call,
            nudge_poll=task.nudge_poll,
            phase="act",
        )
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

    async def _run_tool_loop(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        tools: list[gtypes.Tool],
        working_dir: str,
        max_rounds: int,
        max_tokens: int,
        on_event: Any = None,
        on_tool_call: Any = None,
        nudge_poll: Any = None,
        phase: str = "",
    ) -> _PhaseResult:
        """Run the tool-use loop for a single phase. Core reusable engine."""
        contents: list[gtypes.Content] = [
            gtypes.Content(parts=[gtypes.Part(text=user_prompt)], role="user"),
        ]
        total_input = 0
        total_output = 0
        all_tool_calls: list[dict[str, Any]] = []
        final_text = ""
        round_num = 0

        config = gtypes.GenerateContentConfig(
            system_instruction=system_prompt,
            max_output_tokens=max_tokens,
            tools=tools if tools else None,
        )

        for round_num in range(max_rounds):
            async def _on_retry(wait: int) -> None:
                if on_event:
                    await on_event("output", {
                        "text": f"[Rate limited ({phase}) — waiting {wait}s before retrying...]",
                        "round": round_num,
                    })

            response = await self._call_with_retry(
                lambda: self._client.aio.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config,
                ),
                label=phase,
                on_retry=_on_retry,
            )

            # Extract token usage
            usage = response.usage_metadata
            input_tokens = usage.prompt_token_count or 0 if usage else 0
            output_tokens = usage.candidates_token_count or 0 if usage else 0
            total_input += input_tokens
            total_output += output_tokens

            # Extract text and function calls from response
            candidate = response.candidates[0] if response.candidates else None
            if not candidate or not candidate.content or not candidate.content.parts:
                break

            text_parts = []
            function_calls = []
            for part in candidate.content.parts:
                if part.text:
                    text_parts.append(part.text)
                elif part.function_call:
                    function_calls.append(part)

            if text_parts:
                final_text = "\n".join(text_parts)
                if on_event:
                    await on_event("output", {"text": final_text, "round": round_num})

            # If no function calls, we're done
            if not function_calls:
                break

            # Add model response to conversation
            contents.append(candidate.content)

            # Execute each function call and build responses
            response_parts: list[gtypes.Part] = []
            for fc_part in function_calls:
                fc = fc_part.function_call
                tool_input = dict(fc.args) if fc.args else {}

                logger.info("[%s] Tool call: %s(%s)", phase, fc.name, json.dumps(tool_input)[:200])
                all_tool_calls.append({"name": fc.name, "input": tool_input})

                if on_event:
                    await on_event("tool_call", {
                        "tool": fc.name, "input": tool_input, "round": round_num,
                    })

                result_text = await execute_tool(fc.name, tool_input, working_dir)

                if on_event:
                    await on_event("tool_result", {
                        "tool": fc.name,
                        "result": result_text[:_MAX_TOOL_RESULT_EVENT_CHARS],
                        "round": round_num,
                    })

                if on_tool_call and not on_event:
                    await on_tool_call(
                        fc.name, tool_input,
                        result_text[:_MAX_TOOL_RESULT_CALLBACK_CHARS],
                    )

                response_parts.append(gtypes.Part(
                    function_response=gtypes.FunctionResponse(
                        name=fc.name,
                        response={"result": result_text},
                    ),
                ))

            contents.append(gtypes.Content(parts=response_parts, role="user"))

            # Check for nudge between rounds
            if nudge_poll:
                nudge = await nudge_poll()
                if nudge:
                    if on_event:
                        await on_event("nudge", {"text": nudge})
                    contents.append(
                        gtypes.Content(
                            parts=[gtypes.Part(text=nudge)], role="user",
                        )
                    )

        cost = _compute_model_cost(model, total_input, total_output)

        return _PhaseResult(
            output=final_text,
            input_tokens=total_input,
            output_tokens=total_output,
            cost_usd=cost,
            tool_calls=all_tool_calls,
            conversation=_serialize_messages(contents),
            round_count=round_num + 1 if contents else 0,
        )

    async def _run_plan_call(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
    ) -> _PhaseResult:
        """Single API call for the plan phase — no tools."""
        async def _plan_api_call() -> Any:
            return await self._client.aio.models.generate_content(
                model=model,
                contents=[
                    gtypes.Content(parts=[gtypes.Part(text=user_prompt)], role="user"),
                ],
                config=gtypes.GenerateContentConfig(
                    system_instruction=system_prompt,
                    max_output_tokens=max_tokens,
                ),
            )

        response = await self._call_with_retry(_plan_api_call, label="plan")

        text = ""
        if response.candidates:
            candidate = response.candidates[0]
            if candidate.content and candidate.content.parts:
                for part in candidate.content.parts:
                    if part.text:
                        text += part.text

        usage = response.usage_metadata
        input_tokens = usage.prompt_token_count or 0 if usage else 0
        output_tokens = usage.candidates_token_count or 0 if usage else 0
        cost = _compute_model_cost(model, input_tokens, output_tokens)

        return _PhaseResult(
            output=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            tool_calls=[],
            conversation=[
                {"role": "user", "content": user_prompt},
                {"role": "model", "content": text},
            ],
            round_count=1,
        )

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    async def stream(self, task: AgentTask) -> AsyncIterator[AgentEvent]:
        """Stream agent events. Yields events as they happen."""
        tools = _make_gemini_tools(task.allowed_tools, task.working_directory)
        contents: list[gtypes.Content] = [
            gtypes.Content(parts=[gtypes.Part(text=task.user_prompt)], role="user"),
        ]

        config = gtypes.GenerateContentConfig(
            system_instruction=task.system_prompt,
            max_output_tokens=task.max_tokens,
            tools=tools if tools else None,
        )

        for round_num in range(task.max_tool_rounds):
            retry_events: list[AgentEvent] = []

            async def _on_stream_retry(wait: int) -> None:
                retry_events.append(AgentEvent(
                    event_type="text_delta",
                    data={"text": f"[Rate limited — waiting {wait}s before retrying...]"},
                ))

            response = await self._call_with_retry(
                lambda: self._client.aio.models.generate_content(
                    model=task.model,
                    contents=contents,
                    config=config,
                ),
                label="stream",
                on_retry=_on_stream_retry,
            )
            for ev in retry_events:
                yield ev

            candidate = response.candidates[0] if response.candidates else None
            if not candidate or not candidate.content or not candidate.content.parts:
                break

            text_parts = []
            function_calls = []
            for part in candidate.content.parts:
                if part.text:
                    text_parts.append(part.text)
                    yield AgentEvent(event_type="text_delta", data={"text": part.text})
                elif part.function_call:
                    function_calls.append(part)
                    yield AgentEvent(
                        event_type="tool_use",
                        data={
                            "name": part.function_call.name,
                            "input": dict(part.function_call.args) if part.function_call.args else {},
                        },
                    )

            if not function_calls:
                break

            contents.append(candidate.content)
            response_parts: list[gtypes.Part] = []
            for fc_part in function_calls:
                fc = fc_part.function_call
                tool_input = dict(fc.args) if fc.args else {}
                result_text = await execute_tool(
                    fc.name, tool_input, task.working_directory or ".",
                )
                response_parts.append(gtypes.Part(
                    function_response=gtypes.FunctionResponse(
                        name=fc.name,
                        response={"result": result_text},
                    ),
                ))
                yield AgentEvent(
                    event_type="tool_result",
                    data={"name": fc.name, "result": result_text[:_MAX_TOOL_RESULT_CALLBACK_CHARS]},
                )
            contents.append(gtypes.Content(parts=response_parts, role="user"))

        yield AgentEvent(event_type="done", data={})
