"""Implementation node — single agent writes tests and code, then verifies."""

from __future__ import annotations

import logging
from typing import Any

from hadron.agent.base import CostAccumulator
from hadron.models.events import EventType, PipelineEvent
from hadron.models.pipeline_state import PipelineState
from hadron.pipeline.nodes import NodeContext, RepoInfo, gather_changed_files, pipeline_node, run_agent
from hadron.config.limits import TEST_OUTPUT_BRIEF_CHARS, TEST_OUTPUT_EVENT_CHARS
from hadron.pipeline.nodes.cr_format import format_cr_section
from hadron.pipeline.testing import run_test_command

logger = logging.getLogger(__name__)


@pipeline_node("implementation")
async def implementation_node(state: PipelineState, ctx: NodeContext, cr_id: str) -> dict[str, Any]:
    """Implementation: single agent writes tests and code, then verifies.

    On first run (review_loop_count == 0), uses the 'implementation' role
    with full explore/plan/act phases. On rework (review_loop_count > 0),
    uses the 'implementation_rework' role for targeted fixes.
    """
    composer = ctx.prompt_composer
    structured_cr = state.get("structured_cr", {})
    costs = CostAccumulator()

    ri = RepoInfo.from_state(state)
    review_loop = state.get("review_loop_count", 0)

    repo_context = composer.build_repo_context(
        agents_md=ri.agents_md,
        directory_tree=state.get("directory_tree", ""),
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

    # Select role based on whether this is initial implementation or rework
    role = "implementation_rework" if review_loop > 0 else "implementation"

    system_prompt = composer.compose_system_prompt(role, repo_context)

    payload = cr_text
    if feature_content:
        payload += f"\n\n## Feature Specifications\n\n{feature_content}"

    user_prompt = composer.compose_user_prompt(payload, review_feedback)

    # Single run_agent call — 3-phase pipeline handles explore/plan/act
    agent_run = await run_agent(
        ctx,
        role=role,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        cr_id=cr_id,
        stage="implementation",
        repo_name=ri.repo_name,
        working_directory=ri.worktree_path,
        loop_iteration=review_loop,
    )
    costs.add(agent_run.result)

    # Authoritative test run after agent finishes
    tests_passing, test_output = await run_test_command(
        ri.worktree_path, ri.test_command, cr_id,
    )

    await ctx.event_bus.emit(PipelineEvent(
        cr_id=cr_id, event_type=EventType.TEST_RUN, stage="implementation",
        data={
            "repo": ri.repo_name,
            "passed": tests_passing,
            "output_tail": test_output[-TEST_OUTPUT_EVENT_CHARS:],
        },
    ))

    # Commit locally — push happens in delivery stage
    await ctx.worktree_manager.commit(
        ri.worktree_path,
        f"feat: implementation for {cr_id} ({'green' if tests_passing else 'red'})",
    )

    dev_result = {
        "repo_name": ri.repo_name,
        "test_files": {},
        "code_files": {},
        "test_output": test_output[-TEST_OUTPUT_BRIEF_CHARS:],
        "tests_passing": tests_passing,
        "dev_iteration": 1,
    }

    await ctx.event_bus.emit(PipelineEvent(
        cr_id=cr_id, event_type=EventType.STAGE_COMPLETED, stage="implementation",
        data={"all_passing": tests_passing},
    ))

    return {
        "dev_results": [dev_result],
        "dev_loop_count": state.get("dev_loop_count", 0) + 1,
        "current_stage": "implementation",
        **costs.to_state_dict(),
        "stage_history": [{"stage": "implementation", "status": "completed"}],
    }
