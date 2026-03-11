"""Delivery node — self_contained strategy: run tests and push branch."""

from __future__ import annotations

from langgraph.types import RunnableConfig

import logging
from typing import Any

from hadron.git.worktree import WorktreeManager
from hadron.models.events import EventType, PipelineEvent
from hadron.models.pipeline_state import PipelineState
from hadron.pipeline.nodes import NodeContext
from hadron.pipeline.testing import run_test_command

logger = logging.getLogger(__name__)


async def delivery_node(state: PipelineState, config: RunnableConfig) -> dict[str, Any]:
    """Self-contained delivery: run full test suite, then push final branch."""
    ctx = NodeContext.from_config(config)
    cr_id = state["cr_id"]

    await ctx.event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_ENTERED, stage="delivery"
        ))

    wm = WorktreeManager(ctx.workspace_dir)

    repo = state.get("repo", {})
    repo_name = repo.get("repo_name", "")
    worktree_path = repo.get("worktree_path", "")
    test_command = (repo.get("test_commands") or ["pytest"])[0]

    # Run full test suite
    tests_passing, test_output = await run_test_command(
        worktree_path, test_command, cr_id,
    )

    # Push branch
    branch_pushed = False
    if tests_passing:
        try:
            await wm.commit_and_push(worktree_path, f"chore: final push for {cr_id}")
            branch_pushed = True
        except RuntimeError as e:
            logger.warning("Push failed for %s: %s", repo_name, e)

    delivery_results = [{
        "repo_name": repo_name,
        "test_output": test_output[-2000:],
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
