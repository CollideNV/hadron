"""Rework node — targeted fixes from review findings, no explore/plan phases."""

from __future__ import annotations

import logging
from typing import Any

from hadron.agent.base import CostAccumulator
from hadron.models.events import EventType, PipelineEvent
from hadron.models.pipeline_state import PipelineState
from hadron.pipeline.nodes import NodeContext, RepoInfo, pipeline_node, run_agent
from hadron.config.limits import TEST_OUTPUT_BRIEF_CHARS, TEST_OUTPUT_EVENT_CHARS
from hadron.pipeline.testing import run_test_command

logger = logging.getLogger(__name__)


def format_review_findings(state: dict[str, Any], repo_name: str) -> str:
    """Format review findings into a concise markdown section."""
    lines = ["## Review Findings to Address\n"]
    for rr in state.get("review_results", []):
        if rr.get("repo_name") == repo_name and rr.get("findings"):
            for f in rr["findings"]:
                lines.append(
                    f"- [{f.get('severity', '')}] {f.get('message', '')} "
                    f"({f.get('file', '')}:{f.get('line', 0)})"
                )
    return "\n".join(lines)


@pipeline_node("implementation")  # Same stage name for UI continuity
async def rework_node(state: PipelineState, ctx: NodeContext, cr_id: str) -> dict[str, Any]:
    """Rework: targeted fixes from review findings.

    Unlike implementation_node, this skips explore/plan phases and uses
    a minimal payload (review findings + CR title only). This saves
    significant cost by avoiding full codebase exploration for what
    should be targeted fixes.
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

    # Minimal payload: just CR title + review findings (no full description, no specs)
    review_feedback = format_review_findings(state, ri.repo_name)
    payload = f"## CR: {structured_cr.get('title', '')}\n\n{review_feedback}"

    system_prompt = composer.compose_system_prompt("implementation_rework", repo_context)
    user_prompt = composer.compose_user_prompt(payload)

    # Single-phase act only — no explore, no plan
    agent_run = await run_agent(
        ctx,
        role="implementation_rework",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        cr_id=cr_id,
        stage="implementation",
        repo_name=ri.repo_name,
        working_directory=ri.worktree_path,
        explore_model="",   # Skip explore phase
        plan_model="",      # Skip plan phase
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
        f"fix: rework for {cr_id} ({'green' if tests_passing else 'red'})",
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
