"""TDD Development node — test writer (red) + code writer (green) loop."""

from __future__ import annotations

import logging
from typing import Any

from hadron.agent.base import CostAccumulator
from hadron.agent.prompt import PromptComposer
from hadron.models.events import EventType, PipelineEvent
from hadron.models.pipeline_state import PipelineState
from hadron.pipeline.nodes import NodeContext, RepoInfo, gather_changed_files, gather_changed_files_multi, gather_files, pipeline_node, run_agent
from hadron.config.limits import TEST_OUTPUT_BRIEF_CHARS, TEST_OUTPUT_EVENT_CHARS, TEST_OUTPUT_TAIL_CHARS
from hadron.pipeline.nodes.cr_format import format_cr_section, format_cr_summary
from hadron.pipeline.testing import run_test_command

logger = logging.getLogger(__name__)


@pipeline_node("tdd")
async def tdd_node(state: PipelineState, ctx: NodeContext, cr_id: str) -> dict[str, Any]:
    """TDD development: write tests (red) → implement code (green) → verify.

    Loops internally up to max_tdd_iterations if tests fail after implementation.
    """
    pipeline_config = state.get("config_snapshot", {}).get("pipeline", {})
    max_iterations = pipeline_config.get("max_tdd_iterations", 5)

    composer = PromptComposer()
    structured_cr = state.get("structured_cr", {})
    costs = CostAccumulator()

    ri = RepoInfo.from_state(state)
    review_loop = state.get("review_loop_count", 0)

    repo_context = composer.build_repo_context(
        agents_md=ri.agents_md,
        languages=ri.languages,
        test_commands=ri.test_commands,
    )

    cr_text = format_cr_section(structured_cr)

    # Include review feedback if this is a retry from review
    review_feedback = ""
    for rr in state.get("review_results", []):
        if rr.get("repo_name") == ri.repo_name and rr.get("findings"):
            review_feedback = "## Review Findings to Address\n\n"
            for f in rr["findings"]:
                review_feedback += f"- [{f.get('severity', '')}] {f.get('message', '')} ({f.get('file', '')}:{f.get('line', 0)})\n"

    # Use cached feature content from behaviour verification if available,
    # otherwise fall back to gathering from git.
    feature_content = state.get("feature_content") or ""
    if not feature_content:
        feature_content = gather_changed_files(ri.worktree_path, "features/**/*.feature", ri.default_branch)

    # === RED PHASE: Write failing tests ===
    await ctx.event_bus.emit(PipelineEvent(
        cr_id=cr_id, event_type=EventType.STAGE_ENTERED, stage="tdd:test_writer",
    ))

    test_system = composer.compose_system_prompt("test_writer", repo_context)
    test_payload = cr_text
    if feature_content:
        test_payload += f"\n\n## Feature Specifications\n\n{feature_content}"
    test_user = composer.compose_user_prompt(test_payload, review_feedback)

    test_run = await run_agent(
        ctx,
        role="test_writer",
        system_prompt=test_system,
        user_prompt=test_user,
        cr_id=cr_id,
        stage="tdd:test_writer",
        repo_name=ri.repo_name,
        working_directory=ri.worktree_path,
        loop_iteration=review_loop,
        # Haiku explores repo structure, Sonnet writes tests
    )
    costs.add(test_run.result)

    await ctx.event_bus.emit(PipelineEvent(
        cr_id=cr_id, event_type=EventType.STAGE_COMPLETED, stage="tdd:test_writer",
    ))

    # === GREEN PHASE: Implement code (with retry loop) ===
    tests_passing = False
    test_output = ""
    iteration = 0

    # Gather test files written by this CR — batch patterns into a single git call
    test_patterns = ["tests/**/test_*.py", "frontend/src/**/*.test.ts*"]
    gathered = gather_changed_files_multi(ri.worktree_path, test_patterns, ri.default_branch)
    test_content = gathered["tests/**/test_*.py"]
    frontend_test_content = gathered["frontend/src/**/*.test.ts*"]
    if frontend_test_content:
        test_content = (test_content + "\n\n" + frontend_test_content).strip()

    # Build the static part of the code writer payload once (CR summary + specs + tests).
    # Only the test output changes between iterations.
    cr_summary = format_cr_summary(structured_cr)
    code_payload_base = cr_summary
    if feature_content:
        code_payload_base += f"\n\n## Feature Specifications\n\n{feature_content}"
    if test_content:
        code_payload_base += f"\n\n## Test Files (your implementation must make these pass)\n\n{test_content}"

    # Run tests to get initial failure output for the code writer
    initial_passing, test_output = await run_test_command(
        ri.worktree_path, ri.test_command, cr_id,
    )

    code_system = composer.compose_system_prompt("code_writer", repo_context)

    await ctx.event_bus.emit(PipelineEvent(
        cr_id=cr_id, event_type=EventType.STAGE_ENTERED, stage="tdd:code_writer",
    ))

    for iteration in range(max_iterations):
        code_payload = code_payload_base
        if test_output:
            code_payload += f"\n\n## Failing Test Output{' (iteration ' + str(iteration) + ')' if iteration > 0 else ''}\n\n```\n{test_output[-TEST_OUTPUT_TAIL_CHARS:]}\n```\n\nFix the implementation to make the failing tests pass."

        code_user = composer.compose_user_prompt(code_payload, review_feedback)

        code_run = await run_agent(
            ctx,
            role="code_writer",
            system_prompt=code_system,
            user_prompt=code_user,
            cr_id=cr_id,
            stage="tdd:code_writer",
            repo_name=ri.repo_name,
            working_directory=ri.worktree_path,
            prior_cost=costs.total_cost,
            loop_iteration=review_loop,
            # Haiku explores repo structure, Sonnet writes code
        )
        costs.add(code_run.result)

        # Run tests
        tests_passing, test_output = await run_test_command(
            ri.worktree_path, ri.test_command, cr_id,
        )

        await ctx.event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.TEST_RUN, stage="tdd:code_writer",
            data={
                "repo": ri.repo_name,
                "passed": tests_passing,
                "iteration": iteration,
                "output_tail": test_output[-TEST_OUTPUT_EVENT_CHARS:],
            },
        ))

        if tests_passing:
            logger.info("Tests passing for %s after iteration %d", ri.repo_name, iteration)
            break
        else:
            logger.info("Tests failing for %s at iteration %d, retrying...", ri.repo_name, iteration)

    await ctx.event_bus.emit(PipelineEvent(
        cr_id=cr_id, event_type=EventType.STAGE_COMPLETED, stage="tdd:code_writer",
        data={"tests_passing": tests_passing, "iterations": iteration + 1},
    ))

    # Commit locally — push happens in delivery stage
    await ctx.worktree_manager.commit(
        ri.worktree_path,
        f"feat: TDD implementation for {cr_id} ({'green' if tests_passing else 'red'})",
    )

    dev_result = {
        "repo_name": ri.repo_name,
        "test_files": {},
        "code_files": {},
        "test_output": test_output[-TEST_OUTPUT_BRIEF_CHARS:],
        "tests_passing": tests_passing,
        "dev_iteration": iteration + 1,
    }

    await ctx.event_bus.emit(PipelineEvent(
        cr_id=cr_id, event_type=EventType.STAGE_COMPLETED, stage="tdd",
        data={"all_passing": tests_passing},
    ))

    return {
        "dev_results": [dev_result],
        "dev_loop_count": state.get("dev_loop_count", 0) + 1,
        "current_stage": "tdd",
        **costs.to_state_dict(),
        "stage_history": [{"stage": "tdd", "status": "completed"}],
    }
