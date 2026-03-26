"""Tests for three-phase agent execution (Explore → Plan → Act)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hadron.agent.base import AgentCallbacks, AgentResult, AgentTask, PhaseConfig
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
    usage.cache_creation_input_tokens = 0
    usage.cache_read_input_tokens = 0

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
    usage.cache_creation_input_tokens = 0
    usage.cache_read_input_tokens = 0

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
                phases=PhaseConfig(
                    explore_model="",
                    plan_model="",
                ),
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
                phases=PhaseConfig(
                    explore_model="",
                    plan_model="",
                ),
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
                phases=PhaseConfig(
                    explore_model="claude-haiku-4-5-20251001",
                    plan_model="",  # No plan phase
                ),
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
                phases=PhaseConfig(
                    explore_model="claude-haiku-4-5-20251001",
                    plan_model="",
                ),
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
                phases=PhaseConfig(
                    explore_model="claude-haiku-4-5-20251001",
                    plan_model="claude-opus-4-20250514",
                ),
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
                phases=PhaseConfig(
                    explore_model="claude-haiku-4-5-20251001",
                    plan_model="claude-opus-4-20250514",
                ),
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
                phases=PhaseConfig(
                    explore_model="claude-haiku-4-5-20251001",
                    plan_model="claude-opus-4-20250514",
                ),
            )
            await backend.execute(task)

        stream_kwargs = mock_stream.call_args.kwargs
        plan_system = stream_kwargs["system"]
        # system is now a list of content blocks with cache_control
        plan_system_text = plan_system[0]["text"] if isinstance(plan_system, list) else plan_system
        assert "You are a code writer. Follow TDD." in plan_system_text


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
                phases=PhaseConfig(
                    explore_model="claude-haiku-4-5-20251001",
                    plan_model="claude-opus-4-20250514",
                ),
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
                phases=PhaseConfig(
                    explore_model="claude-haiku-4-5-20251001",
                    plan_model="claude-opus-4-20250514",
                ),
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
                phases=PhaseConfig(
                    explore_model="claude-haiku-4-5-20251001",
                    plan_model="claude-opus-4-20250514",
                ),
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
                phases=PhaseConfig(
                    explore_model="claude-haiku-4-5-20251001",
                    plan_model="claude-opus-4-20250514",
                ),
                callbacks=AgentCallbacks(
                    on_event=capture_event,
                ),
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
                phases=PhaseConfig(
                    explore_model="",
                    plan_model="",
                ),
                callbacks=AgentCallbacks(
                    on_event=capture_event,
                ),
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
                allowed_tools=["read_file", "list_directory"],
                phases=PhaseConfig(
                    explore_model="claude-haiku-4-5-20251001",
                    plan_model="",  # No plan
                ),
            )
            result = await backend.execute(task)

        # Two calls: explore + act, both Haiku
        assert mock_create.call_count == 2
        for call in mock_create.call_args_list:
            assert call.kwargs["model"] == "claude-haiku-4-5-20251001"


# ---------------------------------------------------------------------------
# Conversation compaction
# ---------------------------------------------------------------------------


class TestConversationCompaction:
    @pytest.mark.asyncio
    async def test_compact_messages_summarizes_middle(self, tmp_workdir):
        """When called with enough messages, compaction summarizes the middle."""
        backend = ClaudeAgentBackend(api_key="test-key")

        summary_response = _make_api_response("Summary: read main.py, found bug in line 10.")

        messages = [
            {"role": "user", "content": "Fix the bug in main.py"},
            {"role": "assistant", "content": [{"type": "text", "text": "Let me read the file."}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "file contents..."}]},
            {"role": "assistant", "content": [{"type": "text", "text": "I see the issue."}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t2", "content": "more results..."}]},
            {"role": "assistant", "content": [{"type": "text", "text": "Writing fix."}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t3", "content": "write ok"}]},
        ]

        with patch.object(backend._client.messages, "create", new_callable=AsyncMock, return_value=summary_response):
            result = await backend._compact_messages(messages, phase="test")

        # Should keep original user, add summary, continue prompt, and tail
        assert result[0] == messages[0]  # Original user preserved
        assert "[Conversation compacted" in result[1]["content"]  # Summary block
        assert "Continue from where you left off" in result[2]["content"]
        assert result[-2:] == messages[-2:]  # Tail preserved
        assert len(result) < len(messages)

    @pytest.mark.asyncio
    async def test_compact_skips_short_conversations(self, tmp_workdir):
        """Compaction is a no-op for short conversations."""
        backend = ClaudeAgentBackend(api_key="test-key")

        messages = [
            {"role": "user", "content": "Do something"},
            {"role": "assistant", "content": "Done."},
        ]
        result = await backend._compact_messages(messages, phase="test")
        assert result is messages  # Unchanged

    @pytest.mark.asyncio
    async def test_compact_survives_api_failure(self, tmp_workdir):
        """If the summary API call fails, original messages are returned."""
        backend = ClaudeAgentBackend(api_key="test-key")

        messages = [
            {"role": "user", "content": "Task"},
            {"role": "assistant", "content": "Step 1"},
            {"role": "user", "content": "result 1"},
            {"role": "assistant", "content": "Step 2"},
            {"role": "user", "content": "result 2"},
            {"role": "assistant", "content": "Step 3"},
            {"role": "user", "content": "result 3"},
        ]

        with patch.object(
            backend._client.messages, "create",
            new_callable=AsyncMock,
            side_effect=Exception("API down"),
        ):
            result = await backend._compact_messages(messages, phase="test")

        assert result is messages  # Unchanged on failure

    @pytest.mark.asyncio
    async def test_compaction_triggered_by_high_input_tokens(self, tmp_workdir):
        """Tool loop triggers compaction when input tokens exceed threshold."""
        # Rounds 1-2: normal tool calls (build up message count)
        tool_r1 = _make_tool_response("read_file", {"path": "a.py"}, tool_id="t1")
        tool_r2 = _make_tool_response("read_file", {"path": "b.py"}, tool_id="t2")
        # Round 3: high token count → triggers compaction (now >= 5 messages)
        tool_r3 = _make_tool_response("read_file", {"path": "c.py"}, tool_id="t3")
        tool_r3.usage.input_tokens = 90_000  # Over threshold
        # Compaction summary call (made by _compact_messages to Haiku)
        summary_response = _make_api_response("Summary of prior work.")
        # Round 4: final response after compaction
        end_response = _make_api_response("Done.", input_tokens=5000, output_tokens=200)

        backend = ClaudeAgentBackend(api_key="test-key")

        with patch.object(
            backend._client.messages, "create",
            new_callable=AsyncMock,
            side_effect=[tool_r1, tool_r2, tool_r3, summary_response, end_response],
        ), patch("hadron.agent.tool_loop.execute_tool", new_callable=AsyncMock, return_value="file contents"):
            events: list[tuple[str, dict]] = []

            async def capture_event(event_type: str, data: dict) -> None:
                events.append((event_type, data))

            task = AgentTask(
                role="code_writer",
                system_prompt="System.",
                user_prompt="Task.",
                working_directory=str(tmp_workdir),
                phases=PhaseConfig(explore_model="", plan_model=""),
                callbacks=AgentCallbacks(on_event=capture_event),
            )
            await backend.execute(task)

        compaction_events = [e for e in events if e[0] == "compaction"]
        assert len(compaction_events) > 0, "Expected compaction event to be emitted"


# ---------------------------------------------------------------------------
# Context reset
# ---------------------------------------------------------------------------


class TestContextReset:
    @pytest.mark.asyncio
    async def test_context_reset_produces_fresh_conversation(self, tmp_workdir):
        """Context reset creates a new conversation with handoff document."""
        backend = ClaudeAgentBackend(api_key="test-key")

        handoff_response = _make_api_response(
            "## Progress\nRead files.\n## Remaining Work\nWrite tests."
        )

        messages = [
            {"role": "user", "content": "Implement feature X"},
            {"role": "assistant", "content": [{"type": "text", "text": "Reading files..."}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "file contents"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "Writing code..."}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t2", "content": "write ok"}]},
        ]

        with patch.object(
            backend._client.messages, "create",
            new_callable=AsyncMock,
            return_value=handoff_response,
        ):
            from hadron.agent.compaction import context_reset
            result = await context_reset(
                backend._client, messages,
                original_task="Implement feature X",
                phase="test",
            )

        # Should be a single user message with original task + handoff
        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert "Implement feature X" in result[0]["content"]
        assert "Handoff from Previous Session" in result[0]["content"]
        assert "## Progress" in result[0]["content"]

    @pytest.mark.asyncio
    async def test_context_reset_falls_back_to_compaction(self, tmp_workdir):
        """If handoff generation fails, falls back to compaction."""
        backend = ClaudeAgentBackend(api_key="test-key")

        # First call (handoff) fails, second call (compaction) succeeds
        compaction_response = _make_api_response("Summary of work so far.")

        messages = [
            {"role": "user", "content": "Implement feature X"},
            {"role": "assistant", "content": [{"type": "text", "text": "Exploring..."}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "result"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "Writing..."}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t2", "content": "ok"}]},
        ]

        with patch.object(
            backend._client.messages, "create",
            new_callable=AsyncMock,
            side_effect=[Exception("API down"), compaction_response],
        ):
            from hadron.agent.compaction import context_reset
            result = await context_reset(
                backend._client, messages,
                original_task="Implement feature X",
                phase="test",
            )

        # Should fall back to compaction (keeps original user + summary + continue + tail)
        assert any("[Conversation compacted" in str(m.get("content", "")) for m in result)

    @pytest.mark.asyncio
    async def test_context_reset_skips_short_conversations(self, tmp_workdir):
        """Very short conversations are returned unchanged."""
        backend = ClaudeAgentBackend(api_key="test-key")

        messages = [
            {"role": "user", "content": "Do something"},
            {"role": "assistant", "content": "Done."},
        ]

        from hadron.agent.compaction import context_reset
        result = await context_reset(
            backend._client, messages,
            original_task="Do something",
            phase="test",
        )
        assert result is messages

    @pytest.mark.asyncio
    async def test_context_reset_triggered_by_very_high_input_tokens(self, tmp_workdir):
        """Tool loop triggers context reset at 150k tokens (not just compaction)."""
        # Build up enough rounds so we have >= 3 messages
        tool_r1 = _make_tool_response("read_file", {"path": "a.py"}, tool_id="t1")
        tool_r2 = _make_tool_response("read_file", {"path": "b.py"}, tool_id="t2")
        # Round 3: very high token count → triggers context reset
        tool_r3 = _make_tool_response("read_file", {"path": "c.py"}, tool_id="t3")
        tool_r3.usage.input_tokens = 160_000  # Over reset threshold
        # Handoff generation call
        handoff_response = _make_api_response("## Progress\nDid stuff.\n## Remaining Work\nFinish.")
        # Final response after reset
        end_response = _make_api_response("Done.", input_tokens=5000, output_tokens=200)

        backend = ClaudeAgentBackend(api_key="test-key")

        with patch.object(
            backend._client.messages, "create",
            new_callable=AsyncMock,
            side_effect=[tool_r1, tool_r2, tool_r3, handoff_response, end_response],
        ), patch("hadron.agent.tool_loop.execute_tool", new_callable=AsyncMock, return_value="file contents"):
            events: list[tuple[str, dict]] = []

            async def capture_event(event_type: str, data: dict) -> None:
                events.append((event_type, data))

            task = AgentTask(
                role="code_writer",
                system_prompt="System.",
                user_prompt="Task.",
                working_directory=str(tmp_workdir),
                phases=PhaseConfig(explore_model="", plan_model=""),
                callbacks=AgentCallbacks(on_event=capture_event),
            )
            await backend.execute(task)

        reset_events = [e for e in events if e[0] == "context_reset"]
        assert len(reset_events) > 0, "Expected context_reset event to be emitted"
