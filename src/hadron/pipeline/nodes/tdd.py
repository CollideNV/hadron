"""TDD Development node — test writer (red) + code writer (green) loop."""

from __future__ import annotations

import logging
from typing import Any

from hadron.agent.base import merge_model_breakdowns
from hadron.agent.prompt import PromptComposer
from hadron.models.events import EventType, PipelineEvent
from hadron.models.pipeline_state import PipelineState
from hadron.pipeline.nodes import NodeContext, RepoInfo, gather_changed_files, gather_files, pipeline_node, run_agent
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
    total_cost = 0.0
    total_input = 0
    total_output = 0
    total_throttle_count = 0
    total_throttle_seconds = 0.0
    total_model_breakdown: dict[str, dict[str, Any]] = {}

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

    # Gather only feature files written/modified by this CR's spec_writer,
    # not unrelated pre-existing specs (e.g. infrastructure features).
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
    total_cost += test_run.result.cost_usd
    total_input += test_run.result.input_tokens
    total_output += test_run.result.output_tokens
    total_throttle_count += test_run.result.throttle_count
    total_throttle_seconds += test_run.result.throttle_seconds
    total_model_breakdown = merge_model_breakdowns(total_model_breakdown, test_run.result.model_breakdown)

    await ctx.event_bus.emit(PipelineEvent(
        cr_id=cr_id, event_type=EventType.STAGE_COMPLETED, stage="tdd:test_writer",
    ))

    # === GREEN PHASE: Implement code (with retry loop) ===
    tests_passing = False
    test_output = ""
    iteration = 0

    # Gather test files and feature specs written by this CR
    test_content = gather_changed_files(ri.worktree_path, "tests/**/test_*.py", ri.default_branch)
    # Also check for frontend test files (*.test.ts, *.test.tsx)
    frontend_test_content = gather_changed_files(ri.worktree_path, "frontend/src/**/*.test.ts*", ri.default_branch)
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
            code_payload += f"\n\n## Failing Test Output{' (iteration ' + str(iteration) + ')' if iteration > 0 else ''}\n\n```\n{test_output[-3000:]}\n```\n\nFix the implementation to make the failing tests pass."

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
            prior_cost=total_cost,
            loop_iteration=review_loop,
            # Haiku explores repo structure, Sonnet writes code
        )
        total_cost += code_run.result.cost_usd
        total_input += code_run.result.input_tokens
        total_output += code_run.result.output_tokens
        total_throttle_count += code_run.result.throttle_count
        total_throttle_seconds += code_run.result.throttle_seconds
        total_model_breakdown = merge_model_breakdowns(total_model_breakdown, code_run.result.model_breakdown)

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
                "output_tail": test_output[-500:],
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
        "test_output": test_output[-2000:],
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
        "cost_input_tokens": total_input,
        "cost_output_tokens": total_output,
        "cost_usd": total_cost,
        "throttle_count": total_throttle_count,
        "throttle_seconds": total_throttle_seconds,
        "model_breakdown": total_model_breakdown,
        "stage_history": [{"stage": "tdd", "status": "completed"}],
    }
