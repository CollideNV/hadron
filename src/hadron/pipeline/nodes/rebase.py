"""Rebase node — rebase feature branch onto latest main."""

from __future__ import annotations

from langgraph.types import RunnableConfig

import asyncio
import logging
from typing import Any

from hadron.git.worktree import WorktreeManager
from hadron.models.events import EventType, PipelineEvent
from hadron.models.pipeline_state import PipelineState

logger = logging.getLogger(__name__)


async def rebase_node(state: PipelineState, config: RunnableConfig) -> dict[str, Any]:
    """Fetch latest main and rebase. If conflicts, pause (MVP: no merge conflict agent)."""
    configurable = config.get("configurable", {})
    event_bus = configurable.get("event_bus")
    workspace_dir = configurable.get("workspace_dir", "/tmp/hadron-workspace")
    cr_id = state["cr_id"]

    if event_bus:
        await event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_ENTERED, stage="rebase"
        ))

    wm = WorktreeManager(workspace_dir)
    all_clean = True
    conflicts = []

    for repo in state.get("affected_repos", []):
        repo_name = repo.get("repo_name", "")
        worktree_path = repo.get("worktree_path", "")
        default_branch = repo.get("default_branch", "main")

        clean = await wm.rebase(worktree_path, default_branch)
        if not clean:
            all_clean = False
            conflicts.append(repo_name)
            logger.warning("Rebase conflicts in %s for CR %s", repo_name, cr_id)

    # If clean, run full test suite
    test_passed = True
    if all_clean:
        for repo in state.get("affected_repos", []):
            worktree_path = repo.get("worktree_path", "")
            test_command = repo.get("test_command", "pytest")
            proc = await asyncio.create_subprocess_shell(
                test_command, cwd=worktree_path,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
            if proc.returncode != 0:
                test_passed = False
                logger.warning("Post-rebase tests failed for %s", repo.get("repo_name", ""))

    if event_bus:
        await event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_COMPLETED, stage="rebase",
            data={"clean": all_clean, "conflicts": conflicts, "tests_passed": test_passed},
        ))

    result: dict[str, Any] = {
        "rebase_clean": all_clean,
        "rebase_conflicts": conflicts,
        "current_stage": "rebase",
        "stage_history": [{"stage": "rebase", "status": "completed"}],
    }

    if not all_clean:
        result["status"] = "paused"
        result["error"] = f"Rebase conflicts in: {', '.join(conflicts)}"

    return result
