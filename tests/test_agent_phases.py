"""Tests for three-phase agent execution (Explore → Plan → Act)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hadron.agent.base import AgentResult, AgentTask
from hadron.agent.claude import (
    ClaudeAgentBackend,
    _MODEL_COSTS,
    _DEFAULT_COST,
    _compute_model_cost,
    _PhaseResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_api_response(text: str, input_tokens: int = 100, output_tokens: int = 50):
    """Build a mock Anthropic API response with a text block and end_turn."""
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = text

    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens

    response = MagicMock()
    response.content = [text_block]
    response.stop_reason = "end_turn"
    response.usage = usage
    return response


def _make_tool_response(tool_name: str, tool_input: dict, tool_id: str = "tu_1",
                        input_tokens: int = 100, output_tokens: int = 50):
    """Build a mock Anthropic API response with a tool_use block."""
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = tool_name
    tool_block.input = tool_input
    tool_block.id = tool_id

    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens

    response = MagicMock()
    response.content = [tool_block]
    response.stop_reason = "tool_use"
    response.usage = usage
    return response


def _make_stream_context(response):
    """Build a mock async context manager for messages.stream() that returns a final message."""

    class _EmptyAsyncIter:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    stream_cm = AsyncMock()
    stream_cm.__aenter__ = AsyncMock(return_value=stream_cm)
    stream_cm.__aexit__ = AsyncMock(return_value=False)
    # Provide a proper async iterator (yields nothing — we only need get_final_message)
    empty = _EmptyAsyncIter()
    stream_cm.__aiter__ = MagicMock(return_value=empty)
    stream_cm.get_final_message = AsyncMock(return_value=response)
    return stream_cm


# ---------------------------------------------------------------------------
# Per-model cost calculation
# ---------------------------------------------------------------------------


class TestModelCosts:
    def test_haiku_cost(self) -> None:
        cost = _compute_model_cost("claude-haiku-4-5-20251001", 1_000_000, 1_000_000)
        assert cost == pytest.approx(0.80 + 4.00)

    def test_sonnet_cost(self) -> None:
        cost = _compute_model_cost("claude-sonnet-4-20250514", 1_000_000, 1_000_000)
        assert cost == pytest.approx(3.00 + 15.00)

    def test_opus_cost(self) -> None:
        cost = _compute_model_cost("claude-opus-4-20250514", 1_000_000, 1_000_000)
        assert cost == pytest.approx(15.00 + 75.00)

    def test_unknown_model_uses_default(self) -> None:
        cost = _compute_model_cost("claude-future-99", 1_000_000, 1_000_000)
        expected = _DEFAULT_COST[0] + _DEFAULT_COST[1]
        assert cost == pytest.approx(expected)

    def test_zero_tokens(self) -> None:
        cost = _compute_model_cost("claude-sonnet-4-20250514", 0, 0)
        assert cost == 0.0


# ---------------------------------------------------------------------------
# Phase skipping (backwards compatibility)
# ---------------------------------------------------------------------------


class TestPhaseSkipping:
    """When explore_model and plan_model are empty, behaviour is identical to single-phase."""

    @pytest.mark.asyncio
    async def test_no_phases_uses_original_prompt(self, tmp_workdir: Path) -> None:
        backend = ClaudeAgentBackend(api_key="test-key")

        text_response = _make_api_response("Done!")

        with patch.object(backend._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = text_response

            task = AgentTask(
                role="test_role",
                system_prompt="You are a test agent.",
                user_prompt="Do the thing.",
                working_directory=str(tmp_workdir),
                explore_model="",
                plan_model="",
            )
            result = await backend.execute(task)

        assert result.output == "Done!"
        # Only one API call (the act phase)
        assert mock_create.call_count == 1
        call_kwargs = mock_create.call_args
        # User prompt should be passed through unchanged
        assert call_kwargs.kwargs["messages"][0]["content"] == "Do the thing."

    @pytest.mark.asyncio
    async def test_no_phases_cost_uses_act_model(self, tmp_workdir: Path) -> None:
        backend = ClaudeAgentBackend(api_key="test-key")

        text_response = _make_api_response("Done!", input_tokens=1000, output_tokens=500)

        with patch.object(backend._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = text_response

            task = AgentTask(
                role="test_role",
                system_prompt="System.",
                user_prompt="Task.",
                working_directory=str(tmp_workdir),
                model="claude-sonnet-4-20250514",
                explore_model="",
                plan_model="",
            )
            result = await backend.execute(task)

        expected_cost = _compute_model_cost("claude-sonnet-4-20250514", 1000, 500)
        assert result.cost_usd == pytest.approx(expected_cost)


# ---------------------------------------------------------------------------
# Explore phase
# ---------------------------------------------------------------------------


class TestExplorePhase:
    @pytest.mark.asyncio
    async def test_explore_uses_read_only_tools(self, tmp_workdir: Path) -> None:
        backend = ClaudeAgentBackend(api_key="test-key")

        # Explore: one tool call to list_directory, then a text summary
        explore_tool_resp = _make_tool_response("list_directory", {"path": "."})
        explore_text_resp = _make_api_response("## Summary\nFound files.")
        # Act: just finishes
        act_resp = _make_api_response("Implementation done.")

        with patch.object(backend._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = [explore_tool_resp, explore_text_resp, act_resp]

            task = AgentTask(
                role="code_writer",
                system_prompt="Write code.",
                user_prompt="Implement feature X.",
                working_directory=str(tmp_workdir),
                explore_model="claude-haiku-4-5-20251001",
                plan_model="",  # No plan phase
            )
            result = await backend.execute(task)

        # First call should use haiku model
        first_call = mock_create.call_args_list[0]
        assert first_call.kwargs["model"] == "claude-haiku-4-5-20251001"

        # Explore should only have read_file and list_directory tools
        explore_tools = first_call.kwargs["tools"]
        tool_names = {t["name"] for t in explore_tools}
        assert tool_names == {"read_file", "list_directory"}
        assert "write_file" not in tool_names
        assert "run_command" not in tool_names

    @pytest.mark.asyncio
    async def test_explore_summary_passed_to_act(self, tmp_workdir: Path) -> None:
        backend = ClaudeAgentBackend(api_key="test-key")

        explore_resp = _make_api_response("Exploration: found src/ and tests/")
        act_resp = _make_api_response("Done implementing.")

        with patch.object(backend._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = [explore_resp, act_resp]

            task = AgentTask(
                role="code_writer",
                system_prompt="Write code.",
                user_prompt="Implement feature X.",
                working_directory=str(tmp_workdir),
                explore_model="claude-haiku-4-5-20251001",
                plan_model="",
            )
            result = await backend.execute(task)

        # Act phase should receive exploration summary in user prompt
        act_call = mock_create.call_args_list[1]
        act_user_prompt = act_call.kwargs["messages"][0]["content"]
        assert "Exploration: found src/ and tests/" in act_user_prompt
        assert "Implement feature X." in act_user_prompt


# ---------------------------------------------------------------------------
# Plan phase (uses streaming)
# ---------------------------------------------------------------------------


class TestPlanPhase:
    @pytest.mark.asyncio
    async def test_plan_uses_streaming_no_tools(self, tmp_workdir: Path) -> None:
        backend = ClaudeAgentBackend(api_key="test-key")

        explore_resp = _make_api_response("Found codebase structure.")
        plan_resp = _make_api_response("Plan: 1. Create file 2. Add tests", input_tokens=200, output_tokens=100)
        act_resp = _make_api_response("Executed the plan.")

        plan_stream = _make_stream_context(plan_resp)

        with (
            patch.object(backend._client.messages, "create", new_callable=AsyncMock) as mock_create,
            patch.object(backend._client.messages, "stream", return_value=plan_stream) as mock_stream,
        ):
            mock_create.side_effect = [explore_resp, act_resp]

            task = AgentTask(
                role="code_writer",
                system_prompt="Write code.",
                user_prompt="Implement feature X.",
                working_directory=str(tmp_workdir),
                explore_model="claude-haiku-4-5-20251001",
                plan_model="claude-opus-4-20250514",
            )
            result = await backend.execute(task)

        # Plan call should use streaming with opus model
        mock_stream.assert_called_once()
        stream_kwargs = mock_stream.call_args.kwargs
        assert stream_kwargs["model"] == "claude-opus-4-20250514"
        # No tools in plan call
        assert "tools" not in stream_kwargs

    @pytest.mark.asyncio
    async def test_plan_receives_exploration_and_task(self, tmp_workdir: Path) -> None:
        backend = ClaudeAgentBackend(api_key="test-key")

        explore_resp = _make_api_response("Exploration summary here.")
        plan_resp = _make_api_response("Implementation plan.", input_tokens=200, output_tokens=100)
        act_resp = _make_api_response("Done.")

        plan_stream = _make_stream_context(plan_resp)

        with (
            patch.object(backend._client.messages, "create", new_callable=AsyncMock) as mock_create,
            patch.object(backend._client.messages, "stream", return_value=plan_stream) as mock_stream,
        ):
            mock_create.side_effect = [explore_resp, act_resp]

            task = AgentTask(
                role="code_writer",
                system_prompt="Write code.",
                user_prompt="Implement feature X.",
                working_directory=str(tmp_workdir),
                explore_model="claude-haiku-4-5-20251001",
                plan_model="claude-opus-4-20250514",
            )
            await backend.execute(task)

        stream_kwargs = mock_stream.call_args.kwargs
        plan_user = stream_kwargs["messages"][0]["content"]
        assert "Exploration summary here." in plan_user
        assert "Implement feature X." in plan_user

    @pytest.mark.asyncio
    async def test_plan_system_includes_role_instructions(self, tmp_workdir: Path) -> None:
        backend = ClaudeAgentBackend(api_key="test-key")

        explore_resp = _make_api_response("Summary.")
        plan_resp = _make_api_response("Plan.", input_tokens=200, output_tokens=100)
        act_resp = _make_api_response("Done.")

        plan_stream = _make_stream_context(plan_resp)

        with (
            patch.object(backend._client.messages, "create", new_callable=AsyncMock) as mock_create,
            patch.object(backend._client.messages, "stream", return_value=plan_stream) as mock_stream,
        ):
            mock_create.side_effect = [explore_resp, act_resp]

            task = AgentTask(
                role="code_writer",
                system_prompt="You are a code writer. Follow TDD.",
                user_prompt="Task.",
                working_directory=str(tmp_workdir),
                explore_model="claude-haiku-4-5-20251001",
                plan_model="claude-opus-4-20250514",
            )
            await backend.execute(task)

        stream_kwargs = mock_stream.call_args.kwargs
        plan_system = stream_kwargs["system"]
        assert "You are a code writer. Follow TDD." in plan_system


# ---------------------------------------------------------------------------
# Act phase with plan
# ---------------------------------------------------------------------------


class TestActPhase:
    @pytest.mark.asyncio
    async def test_act_receives_plan_and_exploration(self, tmp_workdir: Path) -> None:
        backend = ClaudeAgentBackend(api_key="test-key")

        explore_resp = _make_api_response("Exploration context.")
        plan_resp = _make_api_response("Step 1: do X. Step 2: do Y.", input_tokens=200, output_tokens=100)
        act_resp = _make_api_response("All done.")

        plan_stream = _make_stream_context(plan_resp)

        with (
            patch.object(backend._client.messages, "create", new_callable=AsyncMock) as mock_create,
            patch.object(backend._client.messages, "stream", return_value=plan_stream),
        ):
            mock_create.side_effect = [explore_resp, act_resp]

            task = AgentTask(
                role="code_writer",
                system_prompt="Write code.",
                user_prompt="Implement feature X.",
                working_directory=str(tmp_workdir),
                explore_model="claude-haiku-4-5-20251001",
                plan_model="claude-opus-4-20250514",
            )
            result = await backend.execute(task)

        # Act is the second messages.create call (after explore)
        act_call = mock_create.call_args_list[1]
        act_user = act_call.kwargs["messages"][0]["content"]
        assert "Step 1: do X. Step 2: do Y." in act_user
        assert "Exploration context." in act_user
        assert "Implement feature X." in act_user

    @pytest.mark.asyncio
    async def test_act_uses_default_model(self, tmp_workdir: Path) -> None:
        backend = ClaudeAgentBackend(api_key="test-key")

        explore_resp = _make_api_response("Summary.")
        plan_resp = _make_api_response("Plan.", input_tokens=200, output_tokens=100)
        act_resp = _make_api_response("Done.")

        plan_stream = _make_stream_context(plan_resp)

        with (
            patch.object(backend._client.messages, "create", new_callable=AsyncMock) as mock_create,
            patch.object(backend._client.messages, "stream", return_value=plan_stream),
        ):
            mock_create.side_effect = [explore_resp, act_resp]

            task = AgentTask(
                role="code_writer",
                system_prompt="Write code.",
                user_prompt="Task.",
                working_directory=str(tmp_workdir),
                model="claude-sonnet-4-20250514",
                explore_model="claude-haiku-4-5-20251001",
                plan_model="claude-opus-4-20250514",
            )
            await backend.execute(task)

        act_call = mock_create.call_args_list[1]
        assert act_call.kwargs["model"] == "claude-sonnet-4-20250514"


# ---------------------------------------------------------------------------
# Cost aggregation
# ---------------------------------------------------------------------------


class TestCostAggregation:
    @pytest.mark.asyncio
    async def test_costs_aggregated_across_phases(self, tmp_workdir: Path) -> None:
        backend = ClaudeAgentBackend(api_key="test-key")

        explore_resp = _make_api_response("Summary.", input_tokens=1000, output_tokens=500)
        plan_resp = _make_api_response("Plan.", input_tokens=2000, output_tokens=1000)
        act_resp = _make_api_response("Done.", input_tokens=3000, output_tokens=1500)

        plan_stream = _make_stream_context(plan_resp)

        with (
            patch.object(backend._client.messages, "create", new_callable=AsyncMock) as mock_create,
            patch.object(backend._client.messages, "stream", return_value=plan_stream),
        ):
            mock_create.side_effect = [explore_resp, act_resp]

            task = AgentTask(
                role="code_writer",
                system_prompt="Write code.",
                user_prompt="Task.",
                working_directory=str(tmp_workdir),
                model="claude-sonnet-4-20250514",
                explore_model="claude-haiku-4-5-20251001",
                plan_model="claude-opus-4-20250514",
            )
            result = await backend.execute(task)

        # Total tokens
        assert result.input_tokens == 1000 + 2000 + 3000
        assert result.output_tokens == 500 + 1000 + 1500

        # Cost per phase
        explore_cost = _compute_model_cost("claude-haiku-4-5-20251001", 1000, 500)
        plan_cost = _compute_model_cost("claude-opus-4-20250514", 2000, 1000)
        act_cost = _compute_model_cost("claude-sonnet-4-20250514", 3000, 1500)

        assert result.cost_usd == pytest.approx(explore_cost + plan_cost + act_cost)


# ---------------------------------------------------------------------------
# Phase events
# ---------------------------------------------------------------------------


class TestPhaseEvents:
    @pytest.mark.asyncio
    async def test_phase_events_emitted(self, tmp_workdir: Path) -> None:
        backend = ClaudeAgentBackend(api_key="test-key")
        events: list[tuple[str, dict]] = []

        async def capture_event(event_type: str, data: dict) -> None:
            events.append((event_type, data))

        explore_resp = _make_api_response("Summary.")
        plan_resp = _make_api_response("Plan.", input_tokens=200, output_tokens=100)
        act_resp = _make_api_response("Done.")

        plan_stream = _make_stream_context(plan_resp)

        with (
            patch.object(backend._client.messages, "create", new_callable=AsyncMock) as mock_create,
            patch.object(backend._client.messages, "stream", return_value=plan_stream),
        ):
            mock_create.side_effect = [explore_resp, act_resp]

            task = AgentTask(
                role="code_writer",
                system_prompt="Write code.",
                user_prompt="Task.",
                working_directory=str(tmp_workdir),
                model="claude-sonnet-4-20250514",
                explore_model="claude-haiku-4-5-20251001",
                plan_model="claude-opus-4-20250514",
                on_event=capture_event,
            )
            await backend.execute(task)

        phase_events = [(t, d) for t, d in events if t.startswith("phase_")]

        # Should have started+completed for each of the 3 phases
        started_events = [d for t, d in phase_events if t == "phase_started"]
        completed_events = [d for t, d in phase_events if t == "phase_completed"]

        assert len(started_events) == 3
        assert len(completed_events) == 3

        # Verify phases in order
        assert started_events[0]["phase"] == "explore"
        assert started_events[0]["model"] == "claude-haiku-4-5-20251001"
        assert started_events[1]["phase"] == "plan"
        assert started_events[1]["model"] == "claude-opus-4-20250514"
        assert started_events[2]["phase"] == "act"
        assert started_events[2]["model"] == "claude-sonnet-4-20250514"

    @pytest.mark.asyncio
    async def test_no_phase_events_when_no_phases(self, tmp_workdir: Path) -> None:
        backend = ClaudeAgentBackend(api_key="test-key")
        events: list[tuple[str, dict]] = []

        async def capture_event(event_type: str, data: dict) -> None:
            events.append((event_type, data))

        act_resp = _make_api_response("Done.")

        with patch.object(backend._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = act_resp

            task = AgentTask(
                role="test_role",
                system_prompt="System.",
                user_prompt="Task.",
                working_directory=str(tmp_workdir),
                explore_model="",
                plan_model="",
                on_event=capture_event,
            )
            await backend.execute(task)

        phase_events = [(t, d) for t, d in events if t.startswith("phase_")]
        assert len(phase_events) == 0


# ---------------------------------------------------------------------------
# Explore-only (reviewers pattern)
# ---------------------------------------------------------------------------


class TestExploreOnly:
    @pytest.mark.asyncio
    async def test_explore_only_skips_plan(self, tmp_workdir: Path) -> None:
        """Reviewers use explore_model for both explore and act, skip plan."""
        backend = ClaudeAgentBackend(api_key="test-key")

        explore_resp = _make_api_response("Read the diff.")
        act_resp = _make_api_response('{"review_passed": true, "findings": []}')

        with patch.object(backend._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = [explore_resp, act_resp]

            task = AgentTask(
                role="security_reviewer",
                system_prompt="Review for security.",
                user_prompt="Review this diff.",
                working_directory=str(tmp_workdir),
                model="claude-haiku-4-5-20251001",  # Act also uses Haiku
                explore_model="claude-haiku-4-5-20251001",
                plan_model="",  # No plan
                allowed_tools=["read_file", "list_directory"],
            )
            result = await backend.execute(task)

        # Two calls: explore + act, both Haiku
        assert mock_create.call_count == 2
        for call in mock_create.call_args_list:
            assert call.kwargs["model"] == "claude-haiku-4-5-20251001"
