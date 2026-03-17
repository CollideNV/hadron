"""Tests for the E2E testing pipeline node."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hadron.agent.base import AgentResult
from hadron.pipeline.nodes import AgentRunResult
from hadron.pipeline.nodes.e2e_testing import e2e_testing_node


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(
    workspace_dir: str = "/tmp/test-workspace",
) -> dict[str, Any]:
    """Build a RunnableConfig dict with mocked services."""
    agent_backend = AsyncMock()
    event_bus = AsyncMock()
    event_bus.emit = AsyncMock()

    redis_mock = AsyncMock()
    pipe_mock = AsyncMock()
    pipe_mock.get = MagicMock()
    pipe_mock.delete = MagicMock()
    pipe_mock.execute = AsyncMock(return_value=[None, 0])
    redis_mock.pipeline = MagicMock(return_value=pipe_mock)
    redis_mock.set = AsyncMock()

    worktree_manager = AsyncMock()
    worktree_manager.commit = AsyncMock()
    worktree_manager.get_diff = AsyncMock(return_value="")

    return {
        "configurable": {
            "event_bus": event_bus,
            "agent_backend": agent_backend,
            "workspace_dir": workspace_dir,
            "worktree_manager": worktree_manager,
            "redis": redis_mock,
            "model": "test-model",
            "explore_model": "",
            "plan_model": "",
            "intervention_manager": None,
        },
    }


def _make_agent_run_result(
    output: str = "",
    cost_usd: float = 0.01,
    input_tokens: int = 100,
    output_tokens: int = 50,
) -> AgentRunResult:
    return AgentRunResult(
        result=AgentResult(
            output=output,
            cost_usd=cost_usd,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        ),
        conversation_key="test-conv-key",
    )


def _base_state(**overrides: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "cr_id": "CR-test-001",
        "source": "api",
        "repo": {
            "repo_url": "https://github.com/test/repo.git",
            "repo_name": "test-repo",
            "default_branch": "main",
            "worktree_path": "/tmp/test-worktree",
            "agents_md": "",
            "languages": ["python"],
            "test_commands": ["pytest"],
            "e2e_test_commands": [],
        },
        "structured_cr": {"title": "Add feature", "description": "Add a new feature"},
        "directory_tree": "src/\ntests/\n",
        "config_snapshot": {"pipeline": {}},
        "status": "running",
    }
    state.update(overrides)
    return state


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestE2ETestingNode:
    @pytest.mark.asyncio
    async def test_skips_when_no_commands(self) -> None:
        """Node should skip gracefully when e2e_test_commands is empty."""
        config = _make_config()
        state = _base_state()

        result = await e2e_testing_node(state, config)

        assert result["e2e_passed"] is True
        assert result["e2e_results"][0]["tests_passing"] is True

    @pytest.mark.asyncio
    async def test_runs_tests_and_agent_on_failure(self) -> None:
        """Node should run E2E tests, invoke agent when they fail, and re-run."""
        config = _make_config()
        state = _base_state(
            repo={**_base_state()["repo"], "e2e_test_commands": ["npx playwright test"]},
        )

        with patch("hadron.pipeline.nodes.e2e_testing.run_test_command") as mock_test, \
             patch("hadron.pipeline.nodes.e2e_testing.run_agent", return_value=_make_agent_run_result()) as mock_agent, \
             patch("hadron.pipeline.nodes.e2e_testing.emit_stage_diff"):

            # First run fails, second run (after agent) passes
            mock_test.side_effect = [
                (False, "1 failed"),
                (True, "3 passed"),
            ]

            result = await e2e_testing_node(state, config)

        assert result["e2e_passed"] is True
        assert result["e2e_results"][0]["tests_passing"] is True
        mock_agent.assert_called_once()
        assert mock_test.call_count == 2

    @pytest.mark.asyncio
    async def test_passes_on_first_run_still_invokes_agent(self) -> None:
        """When initial E2E tests fail then agent fixes, tests pass."""
        config = _make_config()
        state = _base_state(
            repo={**_base_state()["repo"], "e2e_test_commands": ["npx playwright test"]},
        )

        with patch("hadron.pipeline.nodes.e2e_testing.run_test_command") as mock_test, \
             patch("hadron.pipeline.nodes.e2e_testing.run_agent", return_value=_make_agent_run_result()), \
             patch("hadron.pipeline.nodes.e2e_testing.emit_stage_diff"):

            mock_test.side_effect = [
                (False, "failed"),
                (True, "3 passed"),
            ]

            result = await e2e_testing_node(state, config)

        assert result["e2e_passed"] is True

    @pytest.mark.asyncio
    async def test_emits_events(self) -> None:
        """Node should emit TEST_RUN and STAGE_COMPLETED events."""
        config = _make_config()
        state = _base_state(
            repo={**_base_state()["repo"], "e2e_test_commands": ["npx playwright test"]},
        )
        event_bus = config["configurable"]["event_bus"]

        with patch("hadron.pipeline.nodes.e2e_testing.run_test_command", return_value=(True, "3 passed")), \
             patch("hadron.pipeline.nodes.e2e_testing.run_agent", return_value=_make_agent_run_result()), \
             patch("hadron.pipeline.nodes.e2e_testing.emit_stage_diff"):

            await e2e_testing_node(state, config)

        event_types = [call.args[0].event_type for call in event_bus.emit.call_args_list]
        assert "stage_entered" in event_types
        assert "test_run" in event_types
        assert "stage_completed" in event_types

    @pytest.mark.asyncio
    async def test_returns_cost_data(self) -> None:
        """Node should accumulate and return cost data."""
        config = _make_config()
        state = _base_state(
            repo={**_base_state()["repo"], "e2e_test_commands": ["npx playwright test"]},
        )

        with patch("hadron.pipeline.nodes.e2e_testing.run_test_command", return_value=(True, "3 passed")), \
             patch("hadron.pipeline.nodes.e2e_testing.run_agent", return_value=_make_agent_run_result(cost_usd=0.05)), \
             patch("hadron.pipeline.nodes.e2e_testing.emit_stage_diff"):

            result = await e2e_testing_node(state, config)

        assert result["cost_usd"] == 0.05
        assert result["current_stage"] == "e2e_testing"

    @pytest.mark.asyncio
    async def test_max_retries_from_config(self) -> None:
        """Node should respect max_e2e_retries from config_snapshot."""
        config = _make_config()
        state = _base_state(
            repo={**_base_state()["repo"], "e2e_test_commands": ["npx playwright test"]},
            config_snapshot={"pipeline": {"max_e2e_retries": 1}},
        )

        with patch("hadron.pipeline.nodes.e2e_testing.run_test_command") as mock_test, \
             patch("hadron.pipeline.nodes.e2e_testing.run_agent", return_value=_make_agent_run_result()), \
             patch("hadron.pipeline.nodes.e2e_testing.emit_stage_diff"):

            # All runs fail
            mock_test.return_value = (False, "still failing")

            result = await e2e_testing_node(state, config)

        assert result["e2e_passed"] is False
        # Initial run + 1 retry (max_retries=1) + 1 final = initial + agent retries
        # The loop runs max_retries+1 times, each calling run_test_command after agent
        # Plus the initial run before the loop
        # Total: 1 (initial) + 2 (max_retries+1 loop iterations) = 3
        assert mock_test.call_count == 3

    @pytest.mark.asyncio
    async def test_no_agent_when_initial_tests_pass(self) -> None:
        """Agent should NOT be invoked if E2E tests pass on first run."""
        config = _make_config()
        state = _base_state(
            repo={**_base_state()["repo"], "e2e_test_commands": ["npx playwright test"]},
        )

        with patch("hadron.pipeline.nodes.e2e_testing.run_test_command") as mock_test, \
             patch("hadron.pipeline.nodes.e2e_testing.run_agent", return_value=_make_agent_run_result()) as mock_agent, \
             patch("hadron.pipeline.nodes.e2e_testing.emit_stage_diff"):

            # Tests pass on initial run
            mock_test.return_value = (True, "5 passed")

            result = await e2e_testing_node(state, config)

        assert result["e2e_passed"] is True
        # Agent runs once (attempt 0 always runs regardless of pass/fail)
        mock_agent.assert_called_once()
        # Initial run + one re-run after agent = 2
        assert mock_test.call_count == 2

    @pytest.mark.asyncio
    async def test_zero_max_retries(self) -> None:
        """With max_e2e_retries=0, only one agent attempt should occur."""
        config = _make_config()
        state = _base_state(
            repo={**_base_state()["repo"], "e2e_test_commands": ["npx playwright test"]},
            config_snapshot={"pipeline": {"max_e2e_retries": 0}},
        )

        with patch("hadron.pipeline.nodes.e2e_testing.run_test_command") as mock_test, \
             patch("hadron.pipeline.nodes.e2e_testing.run_agent", return_value=_make_agent_run_result()) as mock_agent, \
             patch("hadron.pipeline.nodes.e2e_testing.emit_stage_diff"):

            mock_test.return_value = (False, "still failing")

            result = await e2e_testing_node(state, config)

        assert result["e2e_passed"] is False
        mock_agent.assert_called_once()
        # Initial run + 1 re-run after agent = 2
        assert mock_test.call_count == 2

    @pytest.mark.asyncio
    async def test_commit_called_with_result(self) -> None:
        """Node should commit E2E test changes regardless of pass/fail."""
        config = _make_config()
        state = _base_state(
            repo={**_base_state()["repo"], "e2e_test_commands": ["npx playwright test"]},
        )
        wm = config["configurable"]["worktree_manager"]

        with patch("hadron.pipeline.nodes.e2e_testing.run_test_command", return_value=(True, "passed")), \
             patch("hadron.pipeline.nodes.e2e_testing.run_agent", return_value=_make_agent_run_result()), \
             patch("hadron.pipeline.nodes.e2e_testing.emit_stage_diff"):

            await e2e_testing_node(state, config)

        wm.commit.assert_called_once()
        commit_msg = wm.commit.call_args[0][1]
        assert "green" in commit_msg
