"""Tests for pipeline node functions.

Each node takes (state: PipelineState, config: RunnableConfig) and returns
a dict of state updates. We mock the agent backend, event bus, WorktreeManager,
and other infrastructure to test each node's logic in isolation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hadron.agent.base import AgentResult
from hadron.pipeline.nodes import AgentRunResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(
    agent_output: str = "",
    agent_cost: float = 0.01,
    agent_input_tokens: int = 100,
    agent_output_tokens: int = 50,
    workspace_dir: str = "/tmp/test-workspace",
    extra_configurable: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a RunnableConfig dict with mocked services."""
    agent_result = AgentResult(
        output=agent_output,
        cost_usd=agent_cost,
        input_tokens=agent_input_tokens,
        output_tokens=agent_output_tokens,
    )
    agent_backend = AsyncMock()
    agent_backend.execute = AsyncMock(return_value=agent_result)

    event_bus = AsyncMock()
    event_bus.emit = AsyncMock()

    redis_mock = AsyncMock()
    pipe_mock = AsyncMock()
    pipe_mock.get = MagicMock()
    pipe_mock.delete = MagicMock()
    pipe_mock.execute = AsyncMock(return_value=[None, 0])
    redis_mock.pipeline = MagicMock(return_value=pipe_mock)
    redis_mock.set = AsyncMock()

    configurable = {
        "event_bus": event_bus,
        "agent_backend": agent_backend,
        "workspace_dir": workspace_dir,
        "redis": redis_mock,
        "model": "test-model",
        "explore_model": "",
        "plan_model": "",
        "intervention_manager": None,
    }
    if extra_configurable:
        configurable.update(extra_configurable)
    return {"configurable": configurable}


def _make_agent_run_result(
    output: str = "",
    cost_usd: float = 0.01,
    input_tokens: int = 100,
    output_tokens: int = 50,
) -> AgentRunResult:
    """Build an AgentRunResult for patching run_agent."""
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
    """Build a minimal PipelineState dict."""
    state: dict[str, Any] = {
        "cr_id": "CR-abc123",
        "source": "api",
        "raw_cr_text": "Add a login endpoint",
        "raw_cr_title": "Login Feature",
        "structured_cr": {
            "title": "Login Feature",
            "description": "Add a login endpoint",
            "acceptance_criteria": ["Users can log in with email and password"],
            "affected_domains": ["auth"],
            "priority": "medium",
            "constraints": [],
            "risk_flags": [],
        },
        "repo": {
            "repo_url": "https://github.com/test/repo.git",
            "repo_name": "repo",
            "default_branch": "main",
            "worktree_path": "/tmp/test-workspace/runs/cr-CR-abc123/repo",
            "agents_md": "",
            "languages": ["python"],
            "test_commands": ["pytest"],
        },
        "behaviour_specs": [],
        "review_results": [],
        "config_snapshot": {"pipeline": {"max_tdd_iterations": 5}},
        "verification_loop_count": 0,
        "dev_loop_count": 0,
        "review_loop_count": 0,
    }
    state.update(overrides)
    return state


# ===========================================================================
# Intake Node
# ===========================================================================


class TestIntakeNode:
    """Tests for intake_node."""

    @pytest.mark.asyncio
    async def test_happy_path_valid_json(self) -> None:
        """Agent returns valid JSON -> structured_cr populated, status not paused."""
        from hadron.pipeline.nodes.intake import intake_node

        structured = {
            "title": "Login Feature",
            "description": "Add a login endpoint",
            "acceptance_criteria": ["Users can log in"],
            "affected_domains": ["auth"],
            "priority": "high",
            "constraints": [],
            "risk_flags": [],
        }
        agent_output = json.dumps(structured)

        config = _make_config(agent_output=agent_output)
        state = _base_state()

        with patch("hadron.pipeline.nodes.intake.run_agent", return_value=_make_agent_run_result(output=agent_output)):
            result = await intake_node(state, config)

        assert result["structured_cr"] == structured
        assert result["current_stage"] == "intake"
        assert result.get("status") != "paused"
        assert result["cost_usd"] == 0.01
        assert result["stage_history"] == [{"stage": "intake", "status": "completed"}]

    @pytest.mark.asyncio
    async def test_happy_path_json_in_code_fence(self) -> None:
        """Agent wraps JSON in ```json ... ``` -> still parses correctly."""
        from hadron.pipeline.nodes.intake import intake_node

        structured = {"title": "Test", "description": "desc", "acceptance_criteria": [], "affected_domains": [], "priority": "medium", "constraints": [], "risk_flags": []}
        agent_output = f"Here is the result:\n```json\n{json.dumps(structured)}\n```"

        config = _make_config()
        state = _base_state()

        with patch("hadron.pipeline.nodes.intake.run_agent", return_value=_make_agent_run_result(output=agent_output)):
            result = await intake_node(state, config)

        assert result["structured_cr"] == structured
        assert result.get("status") != "paused"

    @pytest.mark.asyncio
    async def test_error_unparseable_output(self) -> None:
        """Agent returns gibberish -> status=paused, risk_flags includes intake_parse_failed."""
        from hadron.pipeline.nodes.intake import intake_node

        config = _make_config()
        state = _base_state()

        with patch("hadron.pipeline.nodes.intake.run_agent", return_value=_make_agent_run_result(output="This is not JSON at all")):
            result = await intake_node(state, config)

        assert result["status"] == "paused"
        assert "intake_parse_failed" in result["structured_cr"]["risk_flags"]
        assert result["error"] is not None
        assert result["stage_history"] == [{"stage": "intake", "status": "paused"}]

    @pytest.mark.asyncio
    async def test_emits_stage_events(self) -> None:
        """Verify STAGE_ENTERED and STAGE_COMPLETED events are emitted."""
        from hadron.pipeline.nodes.intake import intake_node

        structured = {"title": "Test"}
        config = _make_config()
        state = _base_state()
        event_bus = config["configurable"]["event_bus"]

        with patch("hadron.pipeline.nodes.intake.run_agent", return_value=_make_agent_run_result(output=json.dumps(structured))):
            await intake_node(state, config)

        # Check that emit was called (STAGE_ENTERED + COST_UPDATE from run_agent + STAGE_COMPLETED)
        assert event_bus.emit.call_count >= 1


# ===========================================================================
# Repo ID Node
# ===========================================================================


class TestRepoIdNode:
    """Tests for repo_id_node."""

    @pytest.mark.asyncio
    async def test_happy_path(self) -> None:
        """Repo with valid URL and name passes through."""
        from hadron.pipeline.nodes.repo_id import repo_id_node

        config = _make_config()
        state = _base_state()
        result = await repo_id_node(state, config)

        assert result["current_stage"] == "repo_id"
        assert result["stage_history"] == [{"stage": "repo_id", "status": "completed"}]
        assert result.get("status") != "failed"

    @pytest.mark.asyncio
    async def test_error_no_repo(self) -> None:
        """No repo in state -> failed."""
        from hadron.pipeline.nodes.repo_id import repo_id_node

        config = _make_config()
        state = _base_state(repo={})
        result = await repo_id_node(state, config)

        assert result["status"] == "failed"
        assert "No repository" in result["error"]

    @pytest.mark.asyncio
    async def test_error_no_repo_url(self) -> None:
        """Repo dict exists but no repo_url -> failed."""
        from hadron.pipeline.nodes.repo_id import repo_id_node

        config = _make_config()
        state = _base_state(repo={"repo_name": "test"})
        result = await repo_id_node(state, config)

        assert result["status"] == "failed"
        assert "No repository" in result["error"]

    @pytest.mark.asyncio
    async def test_repo_name_derived_from_url(self) -> None:
        """If repo_name missing, it's derived from repo_url — node still completes."""
        from hadron.pipeline.nodes.repo_id import repo_id_node

        config = _make_config()
        state = _base_state(repo={"repo_url": "https://github.com/org/my-repo.git"})
        result = await repo_id_node(state, config)

        assert result["current_stage"] == "repo_id"
        assert result.get("status") != "failed"


# ===========================================================================
# Worktree Setup Node
# ===========================================================================


class TestWorktreeSetupNode:
    """Tests for worktree_setup_node."""

    @pytest.mark.asyncio
    async def test_happy_path(self, tmp_path: Path) -> None:
        """Clone + worktree created, languages detected, state updated."""
        from hadron.pipeline.nodes.worktree_setup import worktree_setup_node

        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()

        config = _make_config(workspace_dir=str(tmp_path))
        state = _base_state()

        with (
            patch("hadron.pipeline.nodes.worktree_setup.WorktreeManager") as MockWM,
            patch("hadron.pipeline.nodes.worktree_setup.detect_languages_and_tests", return_value=(["python"], ["pytest"])),
        ):
            wm_instance = MockWM.return_value
            wm_instance.clone_bare = AsyncMock()
            wm_instance.create_worktree = AsyncMock(return_value=worktree_path)
            wm_instance.get_directory_tree = AsyncMock(return_value="repo/\n  main.py")

            result = await worktree_setup_node(state, config)

        assert result["repo"]["worktree_path"] == str(worktree_path)
        assert result["repo"]["languages"] == ["python"]
        assert result["repo"]["test_commands"] == ["pytest"]
        assert result["current_stage"] == "worktree_setup"
        assert result["stage_history"] == [{"stage": "worktree_setup", "status": "completed"}]

    @pytest.mark.asyncio
    async def test_agents_md_read(self, tmp_path: Path) -> None:
        """AGENTS.md is read if present in worktree."""
        from hadron.pipeline.nodes.worktree_setup import worktree_setup_node

        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()
        (worktree_path / "AGENTS.md").write_text("# Agent instructions\nUse pytest -x")

        config = _make_config(workspace_dir=str(tmp_path))
        state = _base_state()

        with (
            patch("hadron.pipeline.nodes.worktree_setup.WorktreeManager") as MockWM,
            patch("hadron.pipeline.nodes.worktree_setup.detect_languages_and_tests", return_value=(["python"], ["pytest -x"])),
        ):
            wm_instance = MockWM.return_value
            wm_instance.clone_bare = AsyncMock()
            wm_instance.create_worktree = AsyncMock(return_value=worktree_path)
            wm_instance.get_directory_tree = AsyncMock(return_value="repo/")

            result = await worktree_setup_node(state, config)

        assert "Agent instructions" in result["repo"]["agents_md"]

    @pytest.mark.asyncio
    async def test_claude_md_fallback(self, tmp_path: Path) -> None:
        """CLAUDE.md is used as fallback when AGENTS.md not present."""
        from hadron.pipeline.nodes.worktree_setup import worktree_setup_node

        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()
        (worktree_path / "CLAUDE.md").write_text("# Claude instructions")

        config = _make_config(workspace_dir=str(tmp_path))
        state = _base_state()

        with (
            patch("hadron.pipeline.nodes.worktree_setup.WorktreeManager") as MockWM,
            patch("hadron.pipeline.nodes.worktree_setup.detect_languages_and_tests", return_value=(["python"], ["pytest"])),
        ):
            wm_instance = MockWM.return_value
            wm_instance.clone_bare = AsyncMock()
            wm_instance.create_worktree = AsyncMock(return_value=worktree_path)
            wm_instance.get_directory_tree = AsyncMock(return_value="repo/")

            result = await worktree_setup_node(state, config)

        assert "Claude instructions" in result["repo"]["agents_md"]


# ===========================================================================
# Behaviour Translation Node
# ===========================================================================


class TestBehaviourTranslationNode:
    """Tests for behaviour_translation_node."""

    @pytest.mark.asyncio
    async def test_happy_path(self) -> None:
        """Agent writes specs -> behaviour_specs populated."""
        from hadron.pipeline.nodes.behaviour import behaviour_translation_node

        config = _make_config()
        state = _base_state()

        with patch("hadron.pipeline.nodes.behaviour.run_agent", return_value=_make_agent_run_result(output="Feature files written to disk")):
            result = await behaviour_translation_node(state, config)

        assert len(result["behaviour_specs"]) == 1
        assert result["behaviour_specs"][0]["repo_name"] == "repo"
        assert result["behaviour_specs"][0]["verified"] is False
        assert result["current_stage"] == "behaviour_translation"
        assert result["cost_usd"] == 0.01

    @pytest.mark.asyncio
    async def test_includes_verification_feedback_on_retry(self) -> None:
        """When existing specs have verification_feedback, it's included."""
        from hadron.pipeline.nodes.behaviour import behaviour_translation_node

        config = _make_config()
        state = _base_state(
            behaviour_specs=[{
                "repo_name": "repo",
                "feature_files": {},
                "verified": False,
                "verification_feedback": "Missing scenario for edge case",
                "verification_iteration": 1,
            }],
            verification_loop_count=1,
        )

        with patch("hadron.pipeline.nodes.behaviour.run_agent", return_value=_make_agent_run_result(output="Updated feature files")) as mock_run:
            result = await behaviour_translation_node(state, config)

        assert result["behaviour_specs"][0]["verification_iteration"] == 1

    @pytest.mark.asyncio
    async def test_cost_tracking(self) -> None:
        """Cost fields are populated from agent result."""
        from hadron.pipeline.nodes.behaviour import behaviour_translation_node

        config = _make_config()
        state = _base_state()

        with patch("hadron.pipeline.nodes.behaviour.run_agent", return_value=_make_agent_run_result(cost_usd=0.05, input_tokens=500, output_tokens=300)):
            result = await behaviour_translation_node(state, config)

        assert result["cost_usd"] == 0.05
        assert result["cost_input_tokens"] == 500
        assert result["cost_output_tokens"] == 300


# ===========================================================================
# Behaviour Verification Node
# ===========================================================================


class TestBehaviourVerificationNode:
    """Tests for behaviour_verification_node."""

    @pytest.mark.asyncio
    async def test_happy_path_verified(self, tmp_path: Path) -> None:
        """Verifier says specs are complete -> behaviour_verified=True."""
        from hadron.pipeline.nodes.behaviour import behaviour_verification_node

        verification = {"verified": True, "feedback": "", "missing_scenarios": [], "issues": []}
        agent_output = json.dumps(verification)

        config = _make_config()
        state = _base_state()
        state["repo"]["worktree_path"] = str(tmp_path)

        with patch("hadron.pipeline.nodes.behaviour.run_agent", return_value=_make_agent_run_result(output=agent_output)):
            result = await behaviour_verification_node(state, config)

        assert result["behaviour_verified"] is True
        assert result["verification_loop_count"] == 1
        assert result["behaviour_specs"][0]["verified"] is True

    @pytest.mark.asyncio
    async def test_verification_failed(self, tmp_path: Path) -> None:
        """Verifier says incomplete -> behaviour_verified=False with feedback."""
        from hadron.pipeline.nodes.behaviour import behaviour_verification_node

        verification = {
            "verified": False,
            "feedback": "Missing error handling scenario",
            "missing_scenarios": ["error_handling"],
            "issues": ["No negative test cases"],
        }
        agent_output = json.dumps(verification)

        config = _make_config()
        state = _base_state()
        state["repo"]["worktree_path"] = str(tmp_path)

        with patch("hadron.pipeline.nodes.behaviour.run_agent", return_value=_make_agent_run_result(output=agent_output)):
            result = await behaviour_verification_node(state, config)

        assert result["behaviour_verified"] is False
        assert result["behaviour_specs"][0]["verification_feedback"] == "Missing error handling scenario"

    @pytest.mark.asyncio
    async def test_unparseable_output_treated_as_failed(self, tmp_path: Path) -> None:
        """Verifier returns non-JSON -> treated as verification failure."""
        from hadron.pipeline.nodes.behaviour import behaviour_verification_node

        config = _make_config()
        state = _base_state()
        state["repo"]["worktree_path"] = str(tmp_path)

        with patch("hadron.pipeline.nodes.behaviour.run_agent", return_value=_make_agent_run_result(output="I think the specs look good")):
            result = await behaviour_verification_node(state, config)

        assert result["behaviour_verified"] is False
        assert "not valid JSON" in result["behaviour_specs"][0]["verification_feedback"]

    @pytest.mark.asyncio
    async def test_json_in_code_fence(self, tmp_path: Path) -> None:
        """Verifier wraps JSON in code fence -> still parses."""
        from hadron.pipeline.nodes.behaviour import behaviour_verification_node

        verification = {"verified": True, "feedback": "", "missing_scenarios": [], "issues": []}
        agent_output = f"```json\n{json.dumps(verification)}\n```"

        config = _make_config()
        state = _base_state()
        state["repo"]["worktree_path"] = str(tmp_path)

        with patch("hadron.pipeline.nodes.behaviour.run_agent", return_value=_make_agent_run_result(output=agent_output)):
            result = await behaviour_verification_node(state, config)

        assert result["behaviour_verified"] is True

    @pytest.mark.asyncio
    async def test_loop_count_increments(self, tmp_path: Path) -> None:
        """verification_loop_count increments each call."""
        from hadron.pipeline.nodes.behaviour import behaviour_verification_node

        verification = {"verified": True, "feedback": ""}
        config = _make_config()
        state = _base_state(verification_loop_count=2)
        state["repo"]["worktree_path"] = str(tmp_path)

        with patch("hadron.pipeline.nodes.behaviour.run_agent", return_value=_make_agent_run_result(output=json.dumps(verification))):
            result = await behaviour_verification_node(state, config)

        assert result["verification_loop_count"] == 3


# ===========================================================================
# TDD Node
# ===========================================================================


class TestTddNode:
    """Tests for tdd_node."""

    @pytest.mark.asyncio
    async def test_happy_path_tests_pass_first_try(self) -> None:
        """Test writer + code writer succeed, tests pass on first iteration."""
        from hadron.pipeline.nodes.tdd import tdd_node

        config = _make_config()
        state = _base_state()

        test_writer_result = _make_agent_run_result(output="Tests written", cost_usd=0.02, input_tokens=200, output_tokens=100)
        code_writer_result = _make_agent_run_result(output="Code implemented", cost_usd=0.03, input_tokens=300, output_tokens=150)

        call_count = 0

        async def mock_run_agent(ctx, *, role, **kwargs):
            nonlocal call_count
            call_count += 1
            if role == "test_writer":
                return test_writer_result
            return code_writer_result

        with (
            patch("hadron.pipeline.nodes.tdd.run_agent", side_effect=mock_run_agent),
            patch("hadron.pipeline.nodes.tdd.run_test_command", return_value=(True, "All 5 tests passed")),
            patch("hadron.pipeline.nodes.tdd.WorktreeManager") as MockWM,
        ):
            MockWM.return_value.commit_and_push = AsyncMock()
            result = await tdd_node(state, config)

        assert result["dev_results"][0]["tests_passing"] is True
        assert result["dev_results"][0]["dev_iteration"] == 1
        assert result["cost_usd"] == pytest.approx(0.05)
        assert result["cost_input_tokens"] == 500
        assert result["cost_output_tokens"] == 250
        assert result["dev_loop_count"] == 1

    @pytest.mark.asyncio
    async def test_tests_fail_then_pass_on_retry(self) -> None:
        """Tests fail first iteration, pass second -> 2 iterations."""
        from hadron.pipeline.nodes.tdd import tdd_node

        config = _make_config()
        state = _base_state()

        test_writer_result = _make_agent_run_result(output="Tests written", cost_usd=0.02)
        code_writer_result = _make_agent_run_result(output="Code implemented", cost_usd=0.03)

        async def mock_run_agent(ctx, *, role, **kwargs):
            if role == "test_writer":
                return test_writer_result
            return code_writer_result

        test_call_count = 0

        async def mock_run_test(*args, **kwargs):
            nonlocal test_call_count
            test_call_count += 1
            if test_call_count == 1:
                return (False, "FAILED: test_login")
            return (True, "All tests passed")

        with (
            patch("hadron.pipeline.nodes.tdd.run_agent", side_effect=mock_run_agent),
            patch("hadron.pipeline.nodes.tdd.run_test_command", side_effect=mock_run_test),
            patch("hadron.pipeline.nodes.tdd.WorktreeManager") as MockWM,
        ):
            MockWM.return_value.commit_and_push = AsyncMock()
            result = await tdd_node(state, config)

        assert result["dev_results"][0]["tests_passing"] is True
        assert result["dev_results"][0]["dev_iteration"] == 2

    @pytest.mark.asyncio
    async def test_tests_fail_all_iterations(self) -> None:
        """Tests fail all max_tdd_iterations -> tests_passing=False."""
        from hadron.pipeline.nodes.tdd import tdd_node

        config = _make_config()
        state = _base_state()
        state["config_snapshot"]["pipeline"]["max_tdd_iterations"] = 2

        async def mock_run_agent(ctx, *, role, **kwargs):
            return _make_agent_run_result(output="attempted", cost_usd=0.01)

        with (
            patch("hadron.pipeline.nodes.tdd.run_agent", side_effect=mock_run_agent),
            patch("hadron.pipeline.nodes.tdd.run_test_command", return_value=(False, "FAILED")),
            patch("hadron.pipeline.nodes.tdd.WorktreeManager") as MockWM,
        ):
            MockWM.return_value.commit_and_push = AsyncMock()
            result = await tdd_node(state, config)

        assert result["dev_results"][0]["tests_passing"] is False
        assert result["dev_results"][0]["dev_iteration"] == 2

    @pytest.mark.asyncio
    async def test_commits_work_after_completion(self) -> None:
        """After TDD loop, work is committed via WorktreeManager."""
        from hadron.pipeline.nodes.tdd import tdd_node

        config = _make_config()
        state = _base_state()

        async def mock_run_agent(ctx, *, role, **kwargs):
            return _make_agent_run_result(output="done")

        with (
            patch("hadron.pipeline.nodes.tdd.run_agent", side_effect=mock_run_agent),
            patch("hadron.pipeline.nodes.tdd.run_test_command", return_value=(True, "passed")),
            patch("hadron.pipeline.nodes.tdd.WorktreeManager") as MockWM,
        ):
            commit_mock = AsyncMock()
            MockWM.return_value.commit_and_push = commit_mock
            await tdd_node(state, config)

        commit_mock.assert_awaited_once()
        call_args = commit_mock.call_args
        assert "CR-abc123" in call_args[0][1]  # commit message contains CR ID

    @pytest.mark.asyncio
    async def test_review_feedback_included(self) -> None:
        """When review_results have findings, they are included in code_writer prompt."""
        from hadron.pipeline.nodes.tdd import tdd_node

        config = _make_config()
        state = _base_state(
            review_results=[{
                "repo_name": "repo",
                "findings": [{"severity": "major", "message": "SQL injection risk", "file": "auth.py", "line": 42}],
                "review_passed": False,
            }],
        )

        prompts_seen = []

        async def mock_run_agent(ctx, *, role, user_prompt="", **kwargs):
            prompts_seen.append((role, kwargs.get("user_prompt", user_prompt)))
            return _make_agent_run_result(output="done")

        with (
            patch("hadron.pipeline.nodes.tdd.run_agent", side_effect=mock_run_agent),
            patch("hadron.pipeline.nodes.tdd.run_test_command", return_value=(True, "passed")),
            patch("hadron.pipeline.nodes.tdd.WorktreeManager") as MockWM,
        ):
            MockWM.return_value.commit_and_push = AsyncMock()
            await tdd_node(state, config)

        # The run_agent calls should have happened
        assert len(prompts_seen) >= 2  # test_writer + code_writer


# ===========================================================================
# Review Node
# ===========================================================================


class TestReviewNode:
    """Tests for review_node."""

    @pytest.mark.asyncio
    async def test_happy_path_no_findings(self) -> None:
        """All 3 reviewers return no critical/major findings -> review_passed=True."""
        from hadron.pipeline.nodes.review import review_node

        clean_review = json.dumps({"review_passed": True, "findings": [], "summary": "Looks good"})

        config = _make_config()
        state = _base_state()

        with (
            patch("hadron.pipeline.nodes.review.run_agent", return_value=_make_agent_run_result(output=clean_review)),
            patch("hadron.pipeline.nodes.review.WorktreeManager") as MockWM,
        ):
            MockWM.return_value.get_diff = AsyncMock(return_value="diff --git a/main.py b/main.py\n+print('hello')")
            result = await review_node(state, config)

        assert result["review_passed"] is True
        assert len(result["review_results"]) == 1
        assert result["review_results"][0]["review_passed"] is True

    @pytest.mark.asyncio
    async def test_critical_finding_fails_review(self) -> None:
        """One reviewer finds critical issue -> review_passed=False."""
        from hadron.pipeline.nodes.review import review_node

        security_review = json.dumps({
            "review_passed": False,
            "findings": [{"severity": "critical", "message": "SQL injection", "file": "auth.py", "line": 10}],
        })
        clean_review = json.dumps({"review_passed": True, "findings": []})

        call_count = 0

        async def mock_run_agent(ctx, *, role, **kwargs):
            nonlocal call_count
            call_count += 1
            if role == "security_reviewer":
                return _make_agent_run_result(output=security_review)
            return _make_agent_run_result(output=clean_review)

        config = _make_config()
        state = _base_state()

        with (
            patch("hadron.pipeline.nodes.review.run_agent", side_effect=mock_run_agent),
            patch("hadron.pipeline.nodes.review.WorktreeManager") as MockWM,
        ):
            MockWM.return_value.get_diff = AsyncMock(return_value="diff --git a/auth.py b/auth.py")
            result = await review_node(state, config)

        assert result["review_passed"] is False
        assert any(f["severity"] == "critical" for f in result["review_results"][0]["findings"])

    @pytest.mark.asyncio
    async def test_major_finding_fails_review(self) -> None:
        """Major severity also blocks."""
        from hadron.pipeline.nodes.review import review_node

        major_review = json.dumps({
            "review_passed": False,
            "findings": [{"severity": "major", "message": "No error handling"}],
        })
        clean_review = json.dumps({"review_passed": True, "findings": []})

        async def mock_run_agent(ctx, *, role, **kwargs):
            if role == "quality_reviewer":
                return _make_agent_run_result(output=major_review)
            return _make_agent_run_result(output=clean_review)

        config = _make_config()
        state = _base_state()

        with (
            patch("hadron.pipeline.nodes.review.run_agent", side_effect=mock_run_agent),
            patch("hadron.pipeline.nodes.review.WorktreeManager") as MockWM,
        ):
            MockWM.return_value.get_diff = AsyncMock(return_value="diff --git a/main.py b/main.py")
            result = await review_node(state, config)

        assert result["review_passed"] is False

    @pytest.mark.asyncio
    async def test_minor_findings_pass_review(self) -> None:
        """Minor/info findings don't block review."""
        from hadron.pipeline.nodes.review import review_node

        minor_review = json.dumps({
            "review_passed": True,
            "findings": [{"severity": "minor", "message": "Could use better variable names"}],
        })
        clean_review = json.dumps({"review_passed": True, "findings": []})

        async def mock_run_agent(ctx, *, role, **kwargs):
            if role == "quality_reviewer":
                return _make_agent_run_result(output=minor_review)
            return _make_agent_run_result(output=clean_review)

        config = _make_config()
        state = _base_state()

        with (
            patch("hadron.pipeline.nodes.review.run_agent", side_effect=mock_run_agent),
            patch("hadron.pipeline.nodes.review.WorktreeManager") as MockWM,
        ):
            MockWM.return_value.get_diff = AsyncMock(return_value="diff --git a/main.py b/main.py")
            result = await review_node(state, config)

        assert result["review_passed"] is True

    @pytest.mark.asyncio
    async def test_unparseable_reviewer_output_fails(self) -> None:
        """If a reviewer returns non-JSON, it's treated as failed review."""
        from hadron.pipeline.nodes.review import review_node

        clean_review = json.dumps({"review_passed": True, "findings": []})

        async def mock_run_agent(ctx, *, role, **kwargs):
            if role == "security_reviewer":
                return _make_agent_run_result(output="I cannot parse this into JSON")
            return _make_agent_run_result(output=clean_review)

        config = _make_config()
        state = _base_state()

        with (
            patch("hadron.pipeline.nodes.review.run_agent", side_effect=mock_run_agent),
            patch("hadron.pipeline.nodes.review.WorktreeManager") as MockWM,
        ):
            MockWM.return_value.get_diff = AsyncMock(return_value="diff --git a/main.py b/main.py")
            result = await review_node(state, config)

        # Unparseable output results in a "major" finding -> blocks
        assert result["review_passed"] is False

    @pytest.mark.asyncio
    async def test_review_loop_count_increments(self) -> None:
        """review_loop_count increments."""
        from hadron.pipeline.nodes.review import review_node

        clean_review = json.dumps({"review_passed": True, "findings": []})
        config = _make_config()
        state = _base_state(review_loop_count=1)

        with (
            patch("hadron.pipeline.nodes.review.run_agent", return_value=_make_agent_run_result(output=clean_review)),
            patch("hadron.pipeline.nodes.review.WorktreeManager") as MockWM,
        ):
            MockWM.return_value.get_diff = AsyncMock(return_value="")
            result = await review_node(state, config)

        assert result["review_loop_count"] == 2

    @pytest.mark.asyncio
    async def test_three_reviewers_run_in_parallel(self) -> None:
        """All three reviewer roles are invoked."""
        from hadron.pipeline.nodes.review import review_node

        clean_review = json.dumps({"review_passed": True, "findings": []})
        roles_seen = []

        async def mock_run_agent(ctx, *, role, **kwargs):
            roles_seen.append(role)
            return _make_agent_run_result(output=clean_review)

        config = _make_config()
        state = _base_state()

        with (
            patch("hadron.pipeline.nodes.review.run_agent", side_effect=mock_run_agent),
            patch("hadron.pipeline.nodes.review.WorktreeManager") as MockWM,
        ):
            MockWM.return_value.get_diff = AsyncMock(return_value="")
            await review_node(state, config)

        assert "security_reviewer" in roles_seen
        assert "quality_reviewer" in roles_seen
        assert "spec_compliance_reviewer" in roles_seen

    @pytest.mark.asyncio
    async def test_cost_aggregated_across_reviewers(self) -> None:
        """Costs from all 3 reviewers are summed."""
        from hadron.pipeline.nodes.review import review_node

        clean_review = json.dumps({"review_passed": True, "findings": []})

        async def mock_run_agent(ctx, *, role, **kwargs):
            return _make_agent_run_result(output=clean_review, cost_usd=0.02, input_tokens=100, output_tokens=50)

        config = _make_config()
        state = _base_state()

        with (
            patch("hadron.pipeline.nodes.review.run_agent", side_effect=mock_run_agent),
            patch("hadron.pipeline.nodes.review.WorktreeManager") as MockWM,
        ):
            MockWM.return_value.get_diff = AsyncMock(return_value="")
            result = await review_node(state, config)

        assert result["cost_usd"] == pytest.approx(0.06)
        assert result["cost_input_tokens"] == 300
        assert result["cost_output_tokens"] == 150


# ===========================================================================
# Rebase Node
# ===========================================================================


class TestRebaseNode:
    """Tests for rebase_node."""

    @pytest.mark.asyncio
    async def test_happy_path_clean_rebase(self) -> None:
        """No conflicts -> rebase_clean=True, no agent invoked."""
        from hadron.pipeline.nodes.rebase import rebase_node

        config = _make_config()
        state = _base_state()

        with (
            patch("hadron.pipeline.nodes.rebase.WorktreeManager") as MockWM,
            patch("hadron.pipeline.nodes.rebase.run_test_command", return_value=(True, "All tests passed")),
        ):
            wm = MockWM.return_value
            wm.rebase_keep_conflicts = AsyncMock(return_value=True)
            result = await rebase_node(state, config)

        assert result["rebase_clean"] is True
        assert result["rebase_conflicts"] == []
        assert result.get("status") != "paused"

    @pytest.mark.asyncio
    async def test_conflicts_resolved_by_agent(self) -> None:
        """Conflicts detected -> agent resolves them -> rebase_clean=True."""
        from hadron.pipeline.nodes.rebase import rebase_node

        config = _make_config()
        state = _base_state()

        with (
            patch("hadron.pipeline.nodes.rebase.WorktreeManager") as MockWM,
            patch("hadron.pipeline.nodes.rebase.run_agent", return_value=_make_agent_run_result(output="Conflicts resolved")),
            patch("hadron.pipeline.nodes.rebase.run_test_command", return_value=(True, "All tests passed")),
        ):
            wm = MockWM.return_value
            wm.rebase_keep_conflicts = AsyncMock(return_value=False)
            wm.get_conflict_files = AsyncMock(return_value=["main.py"])
            wm.continue_rebase = AsyncMock(return_value=True)
            result = await rebase_node(state, config)

        assert result["rebase_clean"] is True

    @pytest.mark.asyncio
    async def test_conflicts_unresolved_aborts(self) -> None:
        """Conflicts that cannot be resolved -> rebase_clean=False, status=paused."""
        from hadron.pipeline.nodes.rebase import rebase_node

        config = _make_config()
        state = _base_state()

        with (
            patch("hadron.pipeline.nodes.rebase.WorktreeManager") as MockWM,
            patch("hadron.pipeline.nodes.rebase.run_agent", return_value=_make_agent_run_result(output="Tried to resolve")),
            patch("hadron.pipeline.nodes.rebase.run_test_command", return_value=(True, "passed")),
        ):
            wm = MockWM.return_value
            wm.rebase_keep_conflicts = AsyncMock(return_value=False)
            wm.get_conflict_files = AsyncMock(return_value=["main.py"])
            wm.continue_rebase = AsyncMock(return_value=False)
            wm.abort_rebase = AsyncMock()
            result = await rebase_node(state, config)

        assert result["rebase_clean"] is False
        assert result["status"] == "paused"
        assert "repo" in result["rebase_conflicts"]

    @pytest.mark.asyncio
    async def test_rebase_exception_treated_as_clean(self) -> None:
        """If rebase_keep_conflicts raises an exception, treat as clean (no conflicts)."""
        from hadron.pipeline.nodes.rebase import rebase_node

        config = _make_config()
        state = _base_state()

        with (
            patch("hadron.pipeline.nodes.rebase.WorktreeManager") as MockWM,
            patch("hadron.pipeline.nodes.rebase.run_test_command", return_value=(True, "passed")),
        ):
            wm = MockWM.return_value
            wm.rebase_keep_conflicts = AsyncMock(side_effect=RuntimeError("network error"))
            result = await rebase_node(state, config)

        assert result["rebase_clean"] is True

    @pytest.mark.asyncio
    async def test_post_rebase_test_failure(self) -> None:
        """Clean rebase but tests fail afterward."""
        from hadron.pipeline.nodes.rebase import rebase_node

        config = _make_config()
        state = _base_state()

        with (
            patch("hadron.pipeline.nodes.rebase.WorktreeManager") as MockWM,
            patch("hadron.pipeline.nodes.rebase.run_test_command", return_value=(False, "FAILED: test_login")),
        ):
            wm = MockWM.return_value
            wm.rebase_keep_conflicts = AsyncMock(return_value=True)
            result = await rebase_node(state, config)

        # Rebase was clean even though tests failed
        assert result["rebase_clean"] is True


# ===========================================================================
# Delivery Node
# ===========================================================================


class TestDeliveryNode:
    """Tests for delivery_node."""

    @pytest.mark.asyncio
    async def test_happy_path_tests_pass_and_push(self) -> None:
        """Tests pass, branch pushed -> all_delivered=True."""
        from hadron.pipeline.nodes.delivery import delivery_node

        config = _make_config()
        state = _base_state()

        with (
            patch("hadron.pipeline.nodes.delivery.WorktreeManager") as MockWM,
            patch("hadron.pipeline.nodes.delivery.run_test_command", return_value=(True, "All 10 tests passed")),
        ):
            MockWM.return_value.commit_and_push = AsyncMock()
            result = await delivery_node(state, config)

        assert result["all_delivered"] is True
        assert result["delivery_results"][0]["tests_passing"] is True
        assert result["delivery_results"][0]["branch_pushed"] is True
        assert result["current_stage"] == "delivery"

    @pytest.mark.asyncio
    async def test_tests_fail_no_push(self) -> None:
        """Tests fail -> branch not pushed, all_delivered=False."""
        from hadron.pipeline.nodes.delivery import delivery_node

        config = _make_config()
        state = _base_state()

        with (
            patch("hadron.pipeline.nodes.delivery.WorktreeManager") as MockWM,
            patch("hadron.pipeline.nodes.delivery.run_test_command", return_value=(False, "FAILED: 3 tests")),
        ):
            MockWM.return_value.commit_and_push = AsyncMock()
            result = await delivery_node(state, config)

        assert result["all_delivered"] is False
        assert result["delivery_results"][0]["tests_passing"] is False
        assert result["delivery_results"][0]["branch_pushed"] is False

    @pytest.mark.asyncio
    async def test_push_failure(self) -> None:
        """Tests pass but push fails -> all_delivered=False."""
        from hadron.pipeline.nodes.delivery import delivery_node

        config = _make_config()
        state = _base_state()

        with (
            patch("hadron.pipeline.nodes.delivery.WorktreeManager") as MockWM,
            patch("hadron.pipeline.nodes.delivery.run_test_command", return_value=(True, "All tests passed")),
        ):
            MockWM.return_value.commit_and_push = AsyncMock(side_effect=RuntimeError("push rejected"))
            result = await delivery_node(state, config)

        assert result["all_delivered"] is False
        assert result["delivery_results"][0]["tests_passing"] is True
        assert result["delivery_results"][0]["branch_pushed"] is False

    @pytest.mark.asyncio
    async def test_test_output_truncated(self) -> None:
        """Very long test output is truncated to 2000 chars."""
        from hadron.pipeline.nodes.delivery import delivery_node

        config = _make_config()
        state = _base_state()
        long_output = "x" * 5000

        with (
            patch("hadron.pipeline.nodes.delivery.WorktreeManager") as MockWM,
            patch("hadron.pipeline.nodes.delivery.run_test_command", return_value=(True, long_output)),
        ):
            MockWM.return_value.commit_and_push = AsyncMock()
            result = await delivery_node(state, config)

        assert len(result["delivery_results"][0]["test_output"]) <= 2000


# ===========================================================================
# Release Node
# ===========================================================================


class TestReleaseNode:
    """Tests for release_node."""

    @pytest.mark.asyncio
    async def test_happy_path_generates_pr_description(self) -> None:
        """PR description generated with CR info."""
        from hadron.pipeline.nodes.release import release_node

        config = _make_config()
        state = _base_state()

        with patch("hadron.pipeline.nodes.release.WorktreeManager") as MockWM:
            MockWM.return_value.commit_and_push = AsyncMock()
            result = await release_node(state, config)

        assert len(result["release_results"]) == 1
        pr_desc = result["release_results"][0]["pr_description"]
        assert "Login Feature" in pr_desc
        assert "CR-abc123" in pr_desc
        assert result["release_results"][0]["branch"] == "ai/cr-CR-abc123"
        assert result["current_stage"] == "release"

    @pytest.mark.asyncio
    async def test_pr_description_includes_review_findings(self) -> None:
        """Review findings are included in PR description."""
        from hadron.pipeline.nodes.release import release_node

        config = _make_config()
        state = _base_state(
            review_results=[{
                "repo_name": "repo",
                "findings": [{"severity": "minor", "message": "Consider adding docstring"}],
                "review_passed": True,
            }],
        )

        with patch("hadron.pipeline.nodes.release.WorktreeManager") as MockWM:
            MockWM.return_value.commit_and_push = AsyncMock()
            result = await release_node(state, config)

        pr_desc = result["release_results"][0]["pr_description"]
        assert "Consider adding docstring" in pr_desc

    @pytest.mark.asyncio
    async def test_push_failure_ignored(self) -> None:
        """Push failure is silently caught (may have nothing to push)."""
        from hadron.pipeline.nodes.release import release_node

        config = _make_config()
        state = _base_state()

        with patch("hadron.pipeline.nodes.release.WorktreeManager") as MockWM:
            MockWM.return_value.commit_and_push = AsyncMock(side_effect=RuntimeError("nothing to push"))
            result = await release_node(state, config)

        # Should still complete successfully
        assert result["current_stage"] == "release"
        assert len(result["release_results"]) == 1

    @pytest.mark.asyncio
    async def test_no_review_findings(self) -> None:
        """When no review findings exist, PR body still generated."""
        from hadron.pipeline.nodes.release import release_node

        config = _make_config()
        state = _base_state(review_results=[])

        with patch("hadron.pipeline.nodes.release.WorktreeManager") as MockWM:
            MockWM.return_value.commit_and_push = AsyncMock()
            result = await release_node(state, config)

        pr_desc = result["release_results"][0]["pr_description"]
        assert "Hadron AI Pipeline" in pr_desc

    @pytest.mark.asyncio
    async def test_acceptance_criteria_in_pr(self) -> None:
        """Acceptance criteria from CR appear in PR description."""
        from hadron.pipeline.nodes.release import release_node

        config = _make_config()
        state = _base_state()

        with patch("hadron.pipeline.nodes.release.WorktreeManager") as MockWM:
            MockWM.return_value.commit_and_push = AsyncMock()
            result = await release_node(state, config)

        pr_desc = result["release_results"][0]["pr_description"]
        assert "Users can log in with email and password" in pr_desc


# ===========================================================================
# NodeContext
# ===========================================================================


class TestNodeContext:
    """Tests for NodeContext.from_config."""

    def test_from_config_extracts_all_fields(self) -> None:
        from hadron.pipeline.nodes.context import NodeContext

        config = _make_config()
        ctx = NodeContext.from_config(config)

        assert ctx.event_bus is not None
        assert ctx.agent_backend is not None
        assert ctx.workspace_dir == "/tmp/test-workspace"
        assert ctx.model == "test-model"
        assert ctx.explore_model == ""
        assert ctx.plan_model == ""

    def test_from_config_defaults(self) -> None:
        from hadron.pipeline.nodes.context import NodeContext

        ctx = NodeContext.from_config({"configurable": {}})

        assert ctx.event_bus is None
        assert ctx.agent_backend is None
        assert ctx.redis is None
        assert ctx.model == "claude-sonnet-4-20250514"
        assert ctx.workspace_dir == "/tmp/hadron-workspace"

    def test_from_config_empty(self) -> None:
        from hadron.pipeline.nodes.context import NodeContext

        ctx = NodeContext.from_config({})
        assert ctx.event_bus is None
        assert ctx.model == "claude-sonnet-4-20250514"


# ===========================================================================
# gather_files helper
# ===========================================================================


class TestGatherFiles:
    """Tests for the gather_files helper."""

    def test_gathers_matching_files(self, tmp_path: Path) -> None:
        from hadron.pipeline.nodes import gather_files

        features = tmp_path / "features"
        features.mkdir()
        (features / "login.feature").write_text("Feature: Login")
        (features / "signup.feature").write_text("Feature: Signup")

        result = gather_files(str(tmp_path), "features/*.feature")
        assert "login.feature" in result
        assert "signup.feature" in result
        assert "Feature: Login" in result

    def test_truncates_large_content(self, tmp_path: Path) -> None:
        from hadron.pipeline.nodes import gather_files, MAX_CONTEXT_CHARS

        features = tmp_path / "features"
        features.mkdir()
        # Create a file larger than MAX_CONTEXT_CHARS
        (features / "huge.feature").write_text("x" * (MAX_CONTEXT_CHARS + 1000))

        result = gather_files(str(tmp_path), "features/*.feature")
        assert len(result) <= MAX_CONTEXT_CHARS + 500  # some overhead for formatting

    def test_empty_when_no_matches(self, tmp_path: Path) -> None:
        from hadron.pipeline.nodes import gather_files

        result = gather_files(str(tmp_path), "features/**/*.feature")
        assert result == ""


# ===========================================================================
# AgentRunResult dataclass
# ===========================================================================


class TestAgentRunResult:
    """Tests for AgentRunResult."""

    def test_default_conversation_key(self) -> None:
        r = AgentRunResult(result=AgentResult(output="test"))
        assert r.conversation_key == ""

    def test_with_conversation_key(self) -> None:
        r = AgentRunResult(result=AgentResult(output="test"), conversation_key="key-123")
        assert r.conversation_key == "key-123"
        assert r.result.output == "test"
