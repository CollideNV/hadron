"""Tests for OpenAIAgentBackend — mocked openai SDK."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hadron.agent.base import AgentCallbacks, AgentTask, PhaseConfig
from hadron.agent.cost import _compute_model_cost


# ---------------------------------------------------------------------------
# Mock openai module so tests work without the optional dependency
# ---------------------------------------------------------------------------

def _install_openai_mock():
    """Install a mock openai module into sys.modules and return it."""
    mock_openai = MagicMock()
    mock_openai.RateLimitError = type("RateLimitError", (Exception,), {})
    mock_openai.InternalServerError = type("InternalServerError", (Exception,), {})
    # AsyncOpenAI constructor returns a mock client
    mock_client = MagicMock()
    mock_openai.AsyncOpenAI.return_value = mock_client
    sys.modules["openai"] = mock_openai
    return mock_openai, mock_client


# ---------------------------------------------------------------------------
# Helpers to build mock OpenAI responses
# ---------------------------------------------------------------------------


def _make_text_response(
    text: str, prompt_tokens: int = 100, completion_tokens: int = 50,
) -> MagicMock:
    msg = MagicMock()
    msg.content = text
    msg.tool_calls = None

    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = "stop"

    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens

    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    return response


def _make_tool_response(
    tool_name: str, tool_args: dict, tool_id: str = "call_1",
    prompt_tokens: int = 100, completion_tokens: int = 50,
) -> MagicMock:
    fc = MagicMock()
    fc.name = tool_name
    fc.arguments = json.dumps(tool_args)

    tc = MagicMock()
    tc.id = tool_id
    tc.type = "function"
    tc.function = fc

    msg = MagicMock()
    msg.content = None
    msg.tool_calls = [tc]
    msg.model_dump.return_value = {
        "role": "assistant", "content": None,
        "tool_calls": [{"id": tool_id, "type": "function", "function": {"name": tool_name, "arguments": json.dumps(tool_args)}}],
    }

    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = "tool_calls"

    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens

    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    return response


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestOpenAIBackendExecute:
    @pytest.mark.asyncio
    async def test_single_phase_text_response(self, tmp_workdir: Path) -> None:
        mock_openai, mock_client = _install_openai_mock()
        try:
            # Force reimport with mocked openai
            sys.modules.pop("hadron.agent.openai_backend", None)
            from hadron.agent.openai_backend import OpenAIAgentBackend

            backend = OpenAIAgentBackend(api_key="test-key")
            text_resp = _make_text_response("Done!", prompt_tokens=200, completion_tokens=100)

            backend._client.chat.completions.create = AsyncMock(return_value=text_resp)

            task = AgentTask(
                role="test", system_prompt="sys", user_prompt="do it",
                working_directory=str(tmp_workdir),
                model="gpt-4o",
                phases=PhaseConfig(explore_model="", plan_model=""),
            )
            result = await backend.execute(task)

            assert result.output == "Done!"
            assert result.input_tokens == 200
            assert result.output_tokens == 100
            expected_cost = _compute_model_cost("gpt-4o", 200, 100)
            assert result.cost_usd == pytest.approx(expected_cost)
        finally:
            sys.modules.pop("openai", None)
            sys.modules.pop("hadron.agent.openai_backend", None)

    @pytest.mark.asyncio
    async def test_tool_loop(self, tmp_workdir: Path) -> None:
        mock_openai, mock_client = _install_openai_mock()
        try:
            sys.modules.pop("hadron.agent.openai_backend", None)
            from hadron.agent.openai_backend import OpenAIAgentBackend

            backend = OpenAIAgentBackend(api_key="test-key")
            tool_resp = _make_tool_response("list_directory", {"path": "."})
            text_resp = _make_text_response("Found files.")

            backend._client.chat.completions.create = AsyncMock(side_effect=[tool_resp, text_resp])

            with patch("hadron.agent.openai_backend.execute_tool", new_callable=AsyncMock, return_value="f main.py"):
                task = AgentTask(
                    role="test", system_prompt="sys", user_prompt="list files",
                    working_directory=str(tmp_workdir),
                    model="gpt-4o",
                    phases=PhaseConfig(explore_model="", plan_model=""),
                )
                result = await backend.execute(task)

            assert result.output == "Found files."
            assert len(result.tool_calls) == 1
            assert result.tool_calls[0]["name"] == "list_directory"
        finally:
            sys.modules.pop("openai", None)
            sys.modules.pop("hadron.agent.openai_backend", None)


class TestOpenAIBackendPlan:
    @pytest.mark.asyncio
    async def test_plan_call_no_tools(self, tmp_workdir: Path) -> None:
        mock_openai, mock_client = _install_openai_mock()
        try:
            sys.modules.pop("hadron.agent.openai_backend", None)
            from hadron.agent.openai_backend import OpenAIAgentBackend

            backend = OpenAIAgentBackend(api_key="test-key")

            explore_resp = _make_text_response("Summary", prompt_tokens=100, completion_tokens=50)
            plan_resp = _make_text_response("The plan", prompt_tokens=200, completion_tokens=100)
            act_resp = _make_text_response("Done", prompt_tokens=300, completion_tokens=150)

            backend._client.chat.completions.create = AsyncMock(
                side_effect=[explore_resp, plan_resp, act_resp],
            )

            task = AgentTask(
                role="test", system_prompt="sys", user_prompt="task",
                working_directory=str(tmp_workdir),
                model="gpt-4o",
                phases=PhaseConfig(explore_model="gpt-4o-mini", plan_model="gpt-4o"),
            )
            result = await backend.execute(task)

            assert result.input_tokens == 600
            assert result.output_tokens == 300
        finally:
            sys.modules.pop("openai", None)
            sys.modules.pop("hadron.agent.openai_backend", None)


class TestOpenAIBackendEvents:
    @pytest.mark.asyncio
    async def test_phase_events_emitted(self, tmp_workdir: Path) -> None:
        mock_openai, mock_client = _install_openai_mock()
        try:
            sys.modules.pop("hadron.agent.openai_backend", None)
            from hadron.agent.openai_backend import OpenAIAgentBackend

            backend = OpenAIAgentBackend(api_key="test-key")
            events: list[tuple[str, dict]] = []

            async def capture(event_type: str, data: dict) -> None:
                events.append((event_type, data))

            explore_resp = _make_text_response("Summary")
            plan_resp = _make_text_response("Plan")
            act_resp = _make_text_response("Done")

            backend._client.chat.completions.create = AsyncMock(
                side_effect=[explore_resp, plan_resp, act_resp],
            )

            task = AgentTask(
                role="test", system_prompt="sys", user_prompt="task",
                working_directory=str(tmp_workdir),
                model="gpt-4o",
                phases=PhaseConfig(explore_model="gpt-4o-mini", plan_model="gpt-4o"),
                callbacks=AgentCallbacks(on_event=capture),
            )
            await backend.execute(task)

            phase_started = [d for t, d in events if t == "phase_started"]
            assert len(phase_started) == 3
            assert phase_started[0]["phase"] == "explore"
            assert phase_started[1]["phase"] == "plan"
            assert phase_started[2]["phase"] == "act"
        finally:
            sys.modules.pop("openai", None)
            sys.modules.pop("hadron.agent.openai_backend", None)
