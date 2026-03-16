"""Tests for GeminiAgentBackend — mocked google.genai.Client."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hadron.agent.base import AgentCallbacks, AgentTask, PhaseConfig
from hadron.agent.cost import _compute_model_cost
from hadron.agent.gemini import GeminiAgentBackend


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_text_response(
    text: str, prompt_tokens: int = 100, candidates_tokens: int = 50,
) -> MagicMock:
    part = MagicMock()
    part.text = text
    # function_call must be falsy
    del part.function_call

    content = MagicMock()
    content.parts = [part]

    candidate = MagicMock()
    candidate.content = content

    usage = MagicMock()
    usage.prompt_token_count = prompt_tokens
    usage.candidates_token_count = candidates_tokens

    response = MagicMock()
    response.candidates = [candidate]
    response.usage_metadata = usage
    return response


def _make_fn_call_response(
    fn_name: str, fn_args: dict,
    prompt_tokens: int = 100, candidates_tokens: int = 50,
) -> MagicMock:
    fc = MagicMock()
    fc.name = fn_name
    fc.args = fn_args

    part = MagicMock()
    part.text = None
    part.function_call = fc

    content = MagicMock()
    content.parts = [part]

    candidate = MagicMock()
    candidate.content = content

    usage = MagicMock()
    usage.prompt_token_count = prompt_tokens
    usage.candidates_token_count = candidates_tokens

    response = MagicMock()
    response.candidates = [candidate]
    response.usage_metadata = usage
    return response


def _make_backend() -> GeminiAgentBackend:
    """Create a GeminiAgentBackend with a mocked client."""
    backend = GeminiAgentBackend(api_key="test-key")
    backend._client = MagicMock()
    return backend


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGeminiBackendExecute:
    @pytest.mark.asyncio
    async def test_single_phase_text_response(self, tmp_workdir: Path) -> None:
        backend = _make_backend()
        text_resp = _make_text_response("Done!", prompt_tokens=200, candidates_tokens=100)
        backend._client.aio.models.generate_content = AsyncMock(return_value=text_resp)

        task = AgentTask(
            role="test", system_prompt="sys", user_prompt="do it",
            working_directory=str(tmp_workdir),
            model="gemini-2.5-flash",
            phases=PhaseConfig(explore_model="", plan_model=""),
        )
        result = await backend.execute(task)

        assert result.output == "Done!"
        assert result.input_tokens == 200
        assert result.output_tokens == 100
        expected_cost = _compute_model_cost("gemini-2.5-flash", 200, 100)
        assert result.cost_usd == pytest.approx(expected_cost)

    @pytest.mark.asyncio
    async def test_function_call_loop(self, tmp_workdir: Path) -> None:
        backend = _make_backend()

        fn_resp = _make_fn_call_response("list_directory", {"path": "."})
        text_resp = _make_text_response("Found files.")

        backend._client.aio.models.generate_content = AsyncMock(side_effect=[fn_resp, text_resp])

        with patch("hadron.agent.gemini.execute_tool", new_callable=AsyncMock, return_value="f main.py"):
            task = AgentTask(
                role="test", system_prompt="sys", user_prompt="list files",
                working_directory=str(tmp_workdir),
                model="gemini-2.5-flash",
                phases=PhaseConfig(explore_model="", plan_model=""),
            )
            result = await backend.execute(task)

        assert result.output == "Found files."
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["name"] == "list_directory"


class TestGeminiBackendPlan:
    @pytest.mark.asyncio
    async def test_plan_returns_text(self, tmp_workdir: Path) -> None:
        backend = _make_backend()
        plan_resp = _make_text_response("The plan", prompt_tokens=300, candidates_tokens=200)
        backend._client.aio.models.generate_content = AsyncMock(return_value=plan_resp)

        result = await backend._call_plan(
            model="gemini-2.5-pro",
            system_prompt="plan this",
            user_prompt="task description",
            max_tokens=8192,
        )

        assert result.output == "The plan"
        assert result.input_tokens == 300
        assert result.output_tokens == 200


class TestGeminiBackendEvents:
    @pytest.mark.asyncio
    async def test_phase_events_emitted(self, tmp_workdir: Path) -> None:
        backend = _make_backend()
        events: list[tuple[str, dict]] = []

        async def capture(event_type: str, data: dict) -> None:
            events.append((event_type, data))

        explore_resp = _make_text_response("Summary")
        plan_resp = _make_text_response("Plan")
        act_resp = _make_text_response("Done")

        backend._client.aio.models.generate_content = AsyncMock(
            side_effect=[explore_resp, plan_resp, act_resp],
        )

        task = AgentTask(
            role="test", system_prompt="sys", user_prompt="task",
            working_directory=str(tmp_workdir),
            model="gemini-2.5-flash",
            phases=PhaseConfig(explore_model="gemini-2.0-flash", plan_model="gemini-2.5-pro"),
            callbacks=AgentCallbacks(on_event=capture),
        )
        await backend.execute(task)

        phase_started = [d for t, d in events if t == "phase_started"]
        assert len(phase_started) == 3
        assert phase_started[0]["phase"] == "explore"
        assert phase_started[1]["phase"] == "plan"
        assert phase_started[2]["phase"] == "act"
