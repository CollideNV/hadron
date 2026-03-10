"""TDD Development node — test writer (red) + code writer (green) loop."""

from __future__ import annotations

from langgraph.types import RunnableConfig

import logging
from typing import Any

from hadron.agent.prompt import PromptComposer
from hadron.git.worktree import WorktreeManager
from hadron.models.events import EventType, PipelineEvent
from hadron.models.pipeline_state import PipelineState
from hadron.pipeline.nodes import NodeContext, gather_files, run_agent
from hadron.pipeline.testing import run_test_command

logger = logging.getLogger(__name__)


async def tdd_node(state: PipelineState, config: RunnableConfig) -> dict[str, Any]:
    """TDD development: write tests (red) → implement code (green) → verify.

    Loops internally up to max_tdd_iterations if tests fail after implementation.
    """
    ctx = NodeContext.from_config(config)
    cr_id = state["cr_id"]
    pipeline_config = state.get("config_snapshot", {}).get("pipeline", {})
    max_iterations = pipeline_config.get("max_tdd_iterations", 5)

    if ctx.event_bus:
        await ctx.event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_ENTERED, stage="tdd"
        ))

    composer = PromptComposer()
    structured_cr = state.get("structured_cr", {})
    total_cost = 0.0
    total_input = 0
    total_output = 0

    repo = state.get("repo", {})
    repo_name = repo.get("repo_name", "")
    worktree_path = repo.get("worktree_path", "")
    test_command = repo.get("test_commands", ["pytest"])[0]
    languages = repo.get("languages", [])

    repo_context = composer.build_repo_context(
        agents_md=repo.get("agents_md", ""),
        languages=languages,
        test_commands=repo.get("test_commands", []),
    )

    cr_text = f"""# Change Request

**Title:** {structured_cr.get('title', '')}
**Description:** {structured_cr.get('description', '')}

**Acceptance Criteria:**
{chr(10).join(f'- {c}' for c in structured_cr.get('acceptance_criteria', []))}
"""

    # Include review feedback if this is a retry from review
    review_feedback = ""
    for rr in state.get("review_results", []):
        if rr.get("repo_name") == repo_name and rr.get("findings"):
            review_feedback = "## Review Findings to Address\n\n"
            for f in rr["findings"]:
                review_feedback += f"- [{f.get('severity', '')}] {f.get('message', '')} ({f.get('file', '')}:{f.get('line', 0)})\n"

    # Gather feature files so the test_writer doesn't need to explore
    feature_content = gather_files(worktree_path, "features/**/*.feature")

    # === RED PHASE: Write failing tests ===
    if ctx.event_bus:
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
        repo_name=repo_name,
        working_directory=worktree_path,
        explore_model="",  # No explore/plan — feature files are injected directly
        plan_model="",
    )
    total_cost += test_run.result.cost_usd
    total_input += test_run.result.input_tokens
    total_output += test_run.result.output_tokens

    if ctx.event_bus:
        await ctx.event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_COMPLETED, stage="tdd:test_writer",
        ))

    # === GREEN PHASE: Implement code (with retry loop) ===
    tests_passing = False
    test_output = ""
    iteration = 0

    # Gather test files so the code_writer knows exactly what to implement
    test_content = gather_files(worktree_path, "tests/**/test_*.py")

    if ctx.event_bus:
        await ctx.event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_ENTERED, stage="tdd:code_writer",
        ))

    for iteration in range(max_iterations):
        code_system = composer.compose_system_prompt("code_writer", repo_context)

        code_payload = cr_text
        if test_content:
            code_payload += f"\n\n## Test Files (your implementation must make these pass)\n\n{test_content}"
        if iteration > 0 and test_output:
            code_payload += f"\n\n## Test Failure Output (iteration {iteration})\n\n```\n{test_output[-3000:]}\n```\n\nFix the implementation to make the failing tests pass."

        code_user = composer.compose_user_prompt(code_payload, review_feedback)

        code_run = await run_agent(
            ctx,
            role="code_writer",
            system_prompt=code_system,
            user_prompt=code_user,
            cr_id=cr_id,
            stage="tdd:code_writer",
            repo_name=repo_name,
            working_directory=worktree_path,
            prior_cost=total_cost,
            explore_model="",  # No explore/plan — test files are injected directly
            plan_model="",
        )
        total_cost += code_run.result.cost_usd
        total_input += code_run.result.input_tokens
        total_output += code_run.result.output_tokens

        # Run tests
        tests_passing, test_output = await run_test_command(
            worktree_path, test_command, cr_id,
        )

        if ctx.event_bus:
            await ctx.event_bus.emit(PipelineEvent(
                cr_id=cr_id, event_type=EventType.TEST_RUN, stage="tdd:code_writer",
                data={
                    "repo": repo_name,
                    "passed": tests_passing,
                    "iteration": iteration,
                    "output_tail": test_output[-500:],
                },
            ))

        if tests_passing:
            logger.info("Tests passing for %s after iteration %d", repo_name, iteration)
            break
        else:
            logger.info("Tests failing for %s at iteration %d, retrying...", repo_name, iteration)

    if ctx.event_bus:
        await ctx.event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_COMPLETED, stage="tdd:code_writer",
            data={"tests_passing": tests_passing, "iterations": iteration + 1},
        ))

    # Commit the work
    wm = WorktreeManager(ctx.workspace_dir)
    await wm.commit_and_push(
        worktree_path,
        f"feat: TDD implementation for {cr_id} ({'green' if tests_passing else 'red'})",
    )

    dev_result = {
        "repo_name": repo_name,
        "test_files": {},
        "code_files": {},
        "test_output": test_output[-2000:],
        "tests_passing": tests_passing,
        "dev_iteration": iteration + 1,
    }

    if ctx.event_bus:
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
        "stage_history": [{"stage": "tdd", "status": "completed"}],
    }
