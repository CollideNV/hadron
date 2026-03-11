"""Tests for Gemini agent backend — tool-use loop, three-phase execution, cost tracking."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from hadron.agent.base import AgentCallbacks, AgentResult, AgentTask, PhaseConfig
from hadron.agent.gemini import (
    GeminiAgentBackend,
    _MODEL_COSTS,
    _DEFAULT_COST,
    _compute_model_cost,
    _make_gemini_tools,
    _PhaseResult,
)


# ---------------------------------------------------------------------------
# Helpers — mock Google GenAI API responses
# ---------------------------------------------------------------------------


def _make_usage(input_tokens: int = 100, output_tokens: int = 50):
    """Build a mock UsageMetadata."""
    usage = MagicMock()
    usage.prompt_token_count = input_tokens
    usage.candidates_token_count = output_tokens
    return usage


def _make_text_part(text: str):
    """Build a mock Part with text only."""
    part = MagicMock()
    part.text = text
    part.function_call = None
    part.function_response = None
    return part


def _make_function_call_part(name: str, args: dict, fc_id: str = "fc_1"):
    """Build a mock Part with a function_call."""
    fc = MagicMock()
    fc.name = name
    fc.args = args
    fc.id = fc_id

    part = MagicMock()
    part.text = None
    part.function_call = fc
    part.function_response = None
    return part


def _make_response(
    parts: list,
    input_tokens: int = 100,
    output_tokens: int = 50,
):
    """Build a mock GenerateContentResponse with given parts."""
    content = MagicMock()
    content.parts = parts
    content.role = "model"

    candidate = MagicMock()
    candidate.content = content

    response = MagicMock()
    response.candidates = [candidate]
    response.usage_metadata = _make_usage(input_tokens, output_tokens)
    return response


def _make_text_response(text: str, input_tokens: int = 100, output_tokens: int = 50):
    """Build a mock response with a single text part."""
    return _make_response([_make_text_part(text)], input_tokens, output_tokens)


def _make_tool_response(
    name: str, args: dict,
    input_tokens: int = 100, output_tokens: int = 50,
):
    """Build a mock response with a single function_call part."""
    return _make_response(
        [_make_function_call_part(name, args)],
        input_tokens, output_tokens,
    )


# ---------------------------------------------------------------------------
# Per-model cost calculation
# ---------------------------------------------------------------------------


class TestGeminiModelCosts:
    def test_pro_cost(self) -> None:
        cost = _compute_model_cost("gemini-2.5-pro", 1_000_000, 1_000_000)
        assert cost == pytest.approx(1.25 + 10.00)

    def test_flash_cost(self) -> None:
        cost = _compute_model_cost("gemini-2.5-flash", 1_000_000, 1_000_000)
        assert cost == pytest.approx(0.30 + 2.50)

    def test_flash_lite_cost(self) -> None:
        cost = _compute_model_cost("gemini-2.5-flash-lite", 1_000_000, 1_000_000)
        assert cost == pytest.approx(0.10 + 0.40)

    def test_flash_3_preview_cost(self) -> None:
        cost = _compute_model_cost("gemini-3-flash-preview", 1_000_000, 1_000_000)
        assert cost == pytest.approx(0.50 + 3.00)

    def test_unknown_model_uses_default(self) -> None:
        cost = _compute_model_cost("gemini-future-99", 1_000_000, 1_000_000)
        expected = _DEFAULT_COST[0] + _DEFAULT_COST[1]  # 0.30 + 2.50
        assert cost == pytest.approx(expected)

    def test_zero_tokens(self) -> None:
        cost = _compute_model_cost("gemini-2.5-pro", 0, 0)
        assert cost == 0.0


# ---------------------------------------------------------------------------
# Tool definition translation
# ---------------------------------------------------------------------------


class TestGeminiToolDefinitions:
    def test_make_gemini_tools_translates_definitions(self) -> None:
        tools = _make_gemini_tools(["read_file", "list_directory"], None)
        assert len(tools) == 1  # One Tool object containing declarations
        decls = tools[0].function_declarations
        names = {d.name for d in decls}
        assert names == {"read_file", "list_directory"}

    def test_make_gemini_tools_excludes_unknown(self) -> None:
        tools = _make_gemini_tools(["read_file", "nonexistent_tool"], None)
        decls = tools[0].function_declarations
        assert len(decls) == 1
        assert decls[0].name == "read_file"

    def test_make_gemini_tools_empty_returns_empty(self) -> None:
        tools = _make_gemini_tools([], None)
        assert tools == []

    def test_all_four_tools_translate(self) -> None:
        tools = _make_gemini_tools(
            ["read_file", "write_file", "list_directory", "run_command"], None,
        )
        decls = tools[0].function_declarations
        names = {d.name for d in decls}
        assert names == {"read_file", "write_file", "list_directory", "run_command"}


# ---------------------------------------------------------------------------
# Phase skipping (backwards compatibility)
# ---------------------------------------------------------------------------


class TestGeminiPhaseSkipping:
    @pytest.mark.asyncio
    async def test_no_phases_uses_original_prompt(self, tmp_workdir: Path) -> None:
        backend = GeminiAgentBackend(api_key="test-key")

        text_response = _make_text_response("Done!")

        with patch.object(
            backend._client.aio.models,
            "generate_content",
            new_callable=AsyncMock,
        ) as mock_generate:
            mock_generate.return_value = text_response

            task = AgentTask(
                role="test_role",
                system_prompt="You are a test agent.",
                user_prompt="Do the thing.",
                working_directory=str(tmp_workdir),
                phases=PhaseConfig(explore_model="", plan_model=""),
            )
            result = await backend.execute(task)

        assert result.output == "Done!"
        assert mock_generate.call_count == 1
        # Check user prompt was passed through
        call_kwargs = mock_generate.call_args
        contents = call_kwargs.kwargs["contents"]
        assert contents[0].parts[0].text == "Do the thing."

    @pytest.mark.asyncio
    async def test_no_phases_cost_uses_act_model(self, tmp_workdir: Path) -> None:
        backend = GeminiAgentBackend(api_key="test-key")

        text_response = _make_text_response("Done!", input_tokens=1000, output_tokens=500)

        with patch.object(
            backend._client.aio.models,
            "generate_content",
            new_callable=AsyncMock,
        ) as mock_generate:
            mock_generate.return_value = text_response

            task = AgentTask(
                role="test_role",
                system_prompt="System.",
                user_prompt="Task.",
                working_directory=str(tmp_workdir),
                model="gemini-2.5-flash",
                phases=PhaseConfig(explore_model="", plan_model=""),
            )
            result = await backend.execute(task)

        expected_cost = _compute_model_cost("gemini-2.5-flash", 1000, 500)
        assert result.cost_usd == pytest.approx(expected_cost)


# ---------------------------------------------------------------------------
# Explore phase
# ---------------------------------------------------------------------------


class TestGeminiExplorePhase:
    @pytest.mark.asyncio
    async def test_explore_uses_read_only_tools(self, tmp_workdir: Path) -> None:
        backend = GeminiAgentBackend(api_key="test-key")

        explore_tool_resp = _make_tool_response("list_directory", {"path": "."})
        explore_text_resp = _make_text_response("## Summary\nFound files.")
        act_resp = _make_text_response("Implementation done.")

        with patch.object(
            backend._client.aio.models,
            "generate_content",
            new_callable=AsyncMock,
        ) as mock_generate:
            mock_generate.side_effect = [explore_tool_resp, explore_text_resp, act_resp]

            task = AgentTask(
                role="code_writer",
                system_prompt="Write code.",
                user_prompt="Implement feature X.",
                working_directory=str(tmp_workdir),
                phases=PhaseConfig(explore_model="gemini-2.5-flash", plan_model=""),
            )
            result = await backend.execute(task)

        # First call should use flash model
        first_call = mock_generate.call_args_list[0]
        assert first_call.kwargs["model"] == "gemini-2.5-flash"

        # Explore should only have read_file and list_directory tools
        explore_config = first_call.kwargs["config"]
        tool_names = set()
        if explore_config.tools:
            for tool in explore_config.tools:
                for decl in tool.function_declarations:
                    tool_names.add(decl.name)
        assert tool_names == {"read_file", "list_directory"}
        assert "write_file" not in tool_names
        assert "run_command" not in tool_names

    @pytest.mark.asyncio
    async def test_explore_summary_passed_to_act(self, tmp_workdir: Path) -> None:
        backend = GeminiAgentBackend(api_key="test-key")

        explore_resp = _make_text_response("Exploration: found src/ and tests/")
        act_resp = _make_text_response("Done implementing.")

        with patch.object(
            backend._client.aio.models,
            "generate_content",
            new_callable=AsyncMock,
        ) as mock_generate:
            mock_generate.side_effect = [explore_resp, act_resp]

            task = AgentTask(
                role="code_writer",
                system_prompt="Write code.",
                user_prompt="Implement feature X.",
                working_directory=str(tmp_workdir),
                phases=PhaseConfig(explore_model="gemini-2.5-flash", plan_model=""),
            )
            result = await backend.execute(task)

        # Act phase should receive exploration summary in user prompt
        act_call = mock_generate.call_args_list[1]
        act_contents = act_call.kwargs["contents"]
        act_user_text = act_contents[0].parts[0].text
        assert "Exploration: found src/ and tests/" in act_user_text
        assert "Implement feature X." in act_user_text


# ---------------------------------------------------------------------------
# Plan phase
# ---------------------------------------------------------------------------


class TestGeminiPlanPhase:
    @pytest.mark.asyncio
    async def test_plan_uses_no_tools(self, tmp_workdir: Path) -> None:
        backend = GeminiAgentBackend(api_key="test-key")

        explore_resp = _make_text_response("Found codebase structure.")
        plan_resp = _make_text_response("Plan: 1. Create file 2. Add tests", input_tokens=200, output_tokens=100)
        act_resp = _make_text_response("Executed the plan.")

        with patch.object(
            backend._client.aio.models,
            "generate_content",
            new_callable=AsyncMock,
        ) as mock_generate:
            mock_generate.side_effect = [explore_resp, plan_resp, act_resp]

            task = AgentTask(
                role="code_writer",
                system_prompt="Write code.",
                user_prompt="Implement feature X.",
                working_directory=str(tmp_workdir),
                phases=PhaseConfig(explore_model="gemini-2.5-flash", plan_model="gemini-2.5-pro"),
            )
            result = await backend.execute(task)

        # Plan call is the second generate_content call
        plan_call = mock_generate.call_args_list[1]
        assert plan_call.kwargs["model"] == "gemini-2.5-pro"
        # Plan call should have NO tools
        plan_config = plan_call.kwargs["config"]
        assert plan_config.tools is None

    @pytest.mark.asyncio
    async def test_plan_receives_exploration_and_task(self, tmp_workdir: Path) -> None:
        backend = GeminiAgentBackend(api_key="test-key")

        explore_resp = _make_text_response("Exploration summary here.")
        plan_resp = _make_text_response("Implementation plan.", input_tokens=200, output_tokens=100)
        act_resp = _make_text_response("Done.")

        with patch.object(
            backend._client.aio.models,
            "generate_content",
            new_callable=AsyncMock,
        ) as mock_generate:
            mock_generate.side_effect = [explore_resp, plan_resp, act_resp]

            task = AgentTask(
                role="code_writer",
                system_prompt="Write code.",
                user_prompt="Implement feature X.",
                working_directory=str(tmp_workdir),
                phases=PhaseConfig(explore_model="gemini-2.5-flash", plan_model="gemini-2.5-pro"),
            )
            await backend.execute(task)

        plan_call = mock_generate.call_args_list[1]
        plan_contents = plan_call.kwargs["contents"]
        plan_user_text = plan_contents[0].parts[0].text
        assert "Exploration summary here." in plan_user_text
        assert "Implement feature X." in plan_user_text

    @pytest.mark.asyncio
    async def test_plan_system_includes_role_instructions(self, tmp_workdir: Path) -> None:
        backend = GeminiAgentBackend(api_key="test-key")

        explore_resp = _make_text_response("Summary.")
        plan_resp = _make_text_response("Plan.", input_tokens=200, output_tokens=100)
        act_resp = _make_text_response("Done.")

        with patch.object(
            backend._client.aio.models,
            "generate_content",
            new_callable=AsyncMock,
        ) as mock_generate:
            mock_generate.side_effect = [explore_resp, plan_resp, act_resp]

            task = AgentTask(
                role="code_writer",
                system_prompt="You are a code writer. Follow TDD.",
                user_prompt="Task.",
                working_directory=str(tmp_workdir),
                phases=PhaseConfig(explore_model="gemini-2.5-flash", plan_model="gemini-2.5-pro"),
            )
            await backend.execute(task)

        plan_call = mock_generate.call_args_list[1]
        plan_config = plan_call.kwargs["config"]
        assert "You are a code writer. Follow TDD." in plan_config.system_instruction


# ---------------------------------------------------------------------------
# Act phase with plan
# ---------------------------------------------------------------------------


class TestGeminiActPhase:
    @pytest.mark.asyncio
    async def test_act_receives_plan_and_exploration(self, tmp_workdir: Path) -> None:
        backend = GeminiAgentBackend(api_key="test-key")

        explore_resp = _make_text_response("Exploration context.")
        plan_resp = _make_text_response("Step 1: do X. Step 2: do Y.", input_tokens=200, output_tokens=100)
        act_resp = _make_text_response("All done.")

        with patch.object(
            backend._client.aio.models,
            "generate_content",
            new_callable=AsyncMock,
        ) as mock_generate:
            mock_generate.side_effect = [explore_resp, plan_resp, act_resp]

            task = AgentTask(
                role="code_writer",
                system_prompt="Write code.",
                user_prompt="Implement feature X.",
                working_directory=str(tmp_workdir),
                phases=PhaseConfig(explore_model="gemini-2.5-flash", plan_model="gemini-2.5-pro"),
            )
            result = await backend.execute(task)

        # Act is the third generate_content call
        act_call = mock_generate.call_args_list[2]
        act_contents = act_call.kwargs["contents"]
        act_user_text = act_contents[0].parts[0].text
        assert "Step 1: do X. Step 2: do Y." in act_user_text
        assert "Exploration context." in act_user_text
        assert "Implement feature X." in act_user_text

    @pytest.mark.asyncio
    async def test_act_uses_specified_model(self, tmp_workdir: Path) -> None:
        backend = GeminiAgentBackend(api_key="test-key")

        explore_resp = _make_text_response("Summary.")
        plan_resp = _make_text_response("Plan.", input_tokens=200, output_tokens=100)
        act_resp = _make_text_response("Done.")

        with patch.object(
            backend._client.aio.models,
            "generate_content",
            new_callable=AsyncMock,
        ) as mock_generate:
            mock_generate.side_effect = [explore_resp, plan_resp, act_resp]

            task = AgentTask(
                role="code_writer",
                system_prompt="Write code.",
                user_prompt="Task.",
                working_directory=str(tmp_workdir),
                model="gemini-2.5-flash",
                phases=PhaseConfig(explore_model="gemini-2.5-flash", plan_model="gemini-2.5-pro"),
            )
            await backend.execute(task)

        act_call = mock_generate.call_args_list[2]
        assert act_call.kwargs["model"] == "gemini-2.5-flash"


# ---------------------------------------------------------------------------
# Cost aggregation
# ---------------------------------------------------------------------------


class TestGeminiCostAggregation:
    @pytest.mark.asyncio
    async def test_costs_aggregated_across_phases(self, tmp_workdir: Path) -> None:
        backend = GeminiAgentBackend(api_key="test-key")

        explore_resp = _make_text_response("Summary.", input_tokens=1000, output_tokens=500)
        plan_resp = _make_text_response("Plan.", input_tokens=2000, output_tokens=1000)
        act_resp = _make_text_response("Done.", input_tokens=3000, output_tokens=1500)

        with patch.object(
            backend._client.aio.models,
            "generate_content",
            new_callable=AsyncMock,
        ) as mock_generate:
            mock_generate.side_effect = [explore_resp, plan_resp, act_resp]

            task = AgentTask(
                role="code_writer",
                system_prompt="Write code.",
                user_prompt="Task.",
                working_directory=str(tmp_workdir),
                model="gemini-2.5-flash",
                phases=PhaseConfig(explore_model="gemini-2.5-flash", plan_model="gemini-2.5-pro"),
            )
            result = await backend.execute(task)

        assert result.input_tokens == 1000 + 2000 + 3000
        assert result.output_tokens == 500 + 1000 + 1500

        explore_cost = _compute_model_cost("gemini-2.5-flash", 1000, 500)
        plan_cost = _compute_model_cost("gemini-2.5-pro", 2000, 1000)
        act_cost = _compute_model_cost("gemini-2.5-flash", 3000, 1500)

        assert result.cost_usd == pytest.approx(explore_cost + plan_cost + act_cost)


# ---------------------------------------------------------------------------
# Phase events
# ---------------------------------------------------------------------------


class TestGeminiPhaseEvents:
    @pytest.mark.asyncio
    async def test_phase_events_emitted(self, tmp_workdir: Path) -> None:
        backend = GeminiAgentBackend(api_key="test-key")
        events: list[tuple[str, dict]] = []

        async def capture_event(event_type: str, data: dict) -> None:
            events.append((event_type, data))

        explore_resp = _make_text_response("Summary.")
        plan_resp = _make_text_response("Plan.", input_tokens=200, output_tokens=100)
        act_resp = _make_text_response("Done.")

        with patch.object(
            backend._client.aio.models,
            "generate_content",
            new_callable=AsyncMock,
        ) as mock_generate:
            mock_generate.side_effect = [explore_resp, plan_resp, act_resp]

            task = AgentTask(
                role="code_writer",
                system_prompt="Write code.",
                user_prompt="Task.",
                working_directory=str(tmp_workdir),
                model="gemini-2.5-flash",
                phases=PhaseConfig(explore_model="gemini-2.5-flash", plan_model="gemini-2.5-pro"),
                callbacks=AgentCallbacks(on_event=capture_event),
            )
            await backend.execute(task)

        phase_events = [(t, d) for t, d in events if t.startswith("phase_")]
        started_events = [d for t, d in phase_events if t == "phase_started"]
        completed_events = [d for t, d in phase_events if t == "phase_completed"]

        assert len(started_events) == 3
        assert len(completed_events) == 3

        assert started_events[0]["phase"] == "explore"
        assert started_events[1]["phase"] == "plan"
        assert started_events[2]["phase"] == "act"


# ---------------------------------------------------------------------------
# Tool-use loop
# ---------------------------------------------------------------------------


class TestGeminiToolUseLoop:
    @pytest.mark.asyncio
    async def test_tool_call_and_result(self, tmp_workdir: Path) -> None:
        backend = GeminiAgentBackend(api_key="test-key")

        # First response: function call to read_file
        tool_resp = _make_tool_response("read_file", {"path": "hello.txt"})
        # Second response: text after seeing tool result
        text_resp = _make_text_response("File contains: hello world")

        with patch.object(
            backend._client.aio.models,
            "generate_content",
            new_callable=AsyncMock,
        ) as mock_generate:
            mock_generate.side_effect = [tool_resp, text_resp]

            task = AgentTask(
                role="test_role",
                system_prompt="Read files.",
                user_prompt="Read hello.txt",
                working_directory=str(tmp_workdir),
                phases=PhaseConfig(explore_model="", plan_model=""),
            )
            result = await backend.execute(task)

        assert result.output == "File contains: hello world"
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["name"] == "read_file"
        assert mock_generate.call_count == 2

    @pytest.mark.asyncio
    async def test_tool_events_emitted(self, tmp_workdir: Path) -> None:
        backend = GeminiAgentBackend(api_key="test-key")
        events: list[tuple[str, dict]] = []

        async def capture_event(event_type: str, data: dict) -> None:
            events.append((event_type, data))

        tool_resp = _make_tool_response("read_file", {"path": "hello.txt"})
        text_resp = _make_text_response("Content read.")

        with patch.object(
            backend._client.aio.models,
            "generate_content",
            new_callable=AsyncMock,
        ) as mock_generate:
            mock_generate.side_effect = [tool_resp, text_resp]

            task = AgentTask(
                role="test_role",
                system_prompt="Read files.",
                user_prompt="Read hello.txt",
                working_directory=str(tmp_workdir),
                phases=PhaseConfig(explore_model="", plan_model=""),
                callbacks=AgentCallbacks(on_event=capture_event),
            )
            await backend.execute(task)

        tool_call_events = [e for e in events if e[0] == "tool_call"]
        tool_result_events = [e for e in events if e[0] == "tool_result"]
        assert len(tool_call_events) == 1
        assert tool_call_events[0][1]["tool"] == "read_file"
        assert len(tool_result_events) == 1


# ---------------------------------------------------------------------------
# Factory tests
# ---------------------------------------------------------------------------


class TestBackendFactory:
    def test_claude_model_returns_claude_backend(self) -> None:
        from hadron.agent.factory import get_backend
        backend = get_backend("claude-sonnet-4-20250514", anthropic_api_key="test")
        from hadron.agent.claude import ClaudeAgentBackend
        assert isinstance(backend, ClaudeAgentBackend)

    def test_gemini_model_returns_gemini_backend(self) -> None:
        from hadron.agent.factory import get_backend
        backend = get_backend("gemini-2.5-flash", google_api_key="test")
        assert isinstance(backend, GeminiAgentBackend)

    def test_unknown_model_raises(self) -> None:
        from hadron.agent.factory import get_backend
        with pytest.raises(ValueError, match="Unrecognised model"):
            get_backend("unknown-model-v1")

    def test_is_gemini_model(self) -> None:
        from hadron.agent.factory import is_gemini_model
        assert is_gemini_model("gemini-2.5-pro")
        assert is_gemini_model("gemini-2.5-flash")
        assert not is_gemini_model("claude-sonnet-4-20250514")

    def test_is_claude_model(self) -> None:
        from hadron.agent.factory import is_claude_model
        assert is_claude_model("claude-sonnet-4-20250514")
        assert is_claude_model("claude-opus-4-20250514")
        assert not is_claude_model("gemini-2.5-pro")
