"""Delivery node — self_contained strategy: run tests and push branch."""

from __future__ import annotations

import logging
from typing import Any

from hadron.config.limits import TEST_OUTPUT_BRIEF_CHARS
from hadron.models.events import EventType, PipelineEvent
from hadron.models.pipeline_state import PipelineState
from hadron.pipeline.nodes import NodeContext, RepoInfo, pipeline_node
from hadron.pipeline.testing import run_test_command

logger = logging.getLogger(__name__)


@pipeline_node("delivery")
async def delivery_node(state: PipelineState, ctx: NodeContext, cr_id: str) -> dict[str, Any]:
    """Self-contained delivery: run full test suite, then push final branch."""
    wm = ctx.worktree_manager

    ri = RepoInfo.from_state(state)

    # Run full test suite
    tests_passing, test_output = await run_test_command(
        ri.worktree_path, ri.test_command, cr_id,
    )

    # Push branch
    branch_pushed = False
    if tests_passing:
        try:
            await wm.commit_and_push(ri.worktree_path, f"chore: final push for {cr_id}")
            branch_pushed = True
        except RuntimeError as e:
            logger.warning("Push failed for %s: %s", ri.repo_name, e)

    delivery_results = [{
        "repo_name": ri.repo_name,
        "test_output": test_output[-TEST_OUTPUT_BRIEF_CHARS:],
        "tests_passing": tests_passing,
        "branch_pushed": branch_pushed,
        "pr_url": "",
    }]

    all_delivered = tests_passing and branch_pushed

    await ctx.event_bus.emit(PipelineEvent(
        cr_id=cr_id, event_type=EventType.STAGE_COMPLETED, stage="delivery",
        data={"all_delivered": all_delivered},
    ))

    return {
        "delivery_results": delivery_results,
        "all_delivered": all_delivered,
        "current_stage": "delivery",
        "stage_history": [{"stage": "delivery", "status": "completed"}],
    }
