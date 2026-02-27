"""Delivery node — self_contained strategy: run tests and push branch."""

from __future__ import annotations

from langgraph.types import RunnableConfig

import logging
from typing import Any

from hadron.git.worktree import WorktreeManager
from hadron.models.events import EventType, PipelineEvent
from hadron.models.pipeline_state import PipelineState
from hadron.pipeline.testing import run_test_command

logger = logging.getLogger(__name__)


async def delivery_node(state: PipelineState, config: RunnableConfig) -> dict[str, Any]:
    """Self-contained delivery: run full test suite, then push final branch."""
    configurable = config.get("configurable", {})
    event_bus = configurable.get("event_bus")
    workspace_dir = configurable.get("workspace_dir", "/tmp/hadron-workspace")
    cr_id = state["cr_id"]

    if event_bus:
        await event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_ENTERED, stage="delivery"
        ))

    wm = WorktreeManager(workspace_dir)
    delivery_results = []

    for repo in state.get("affected_repos", []):
        repo_name = repo.get("repo_name", "")
        worktree_path = repo.get("worktree_path", "")
        test_command = repo.get("test_command", "pytest")

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

        delivery_results.append({
            "repo_name": repo_name,
            "test_output": test_output[-2000:],
            "tests_passing": tests_passing,
            "branch_pushed": branch_pushed,
            "pr_url": "",
        })

    all_delivered = all(r["tests_passing"] and r["branch_pushed"] for r in delivery_results)

    if event_bus:
        await event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_COMPLETED, stage="delivery",
            data={"all_delivered": all_delivered},
        ))

    return {
        "delivery_results": delivery_results,
        "all_delivered": all_delivered,
        "current_stage": "delivery",
        "stage_history": [{"stage": "delivery", "status": "completed"}],
    }
