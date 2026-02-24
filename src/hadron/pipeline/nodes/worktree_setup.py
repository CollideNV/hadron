"""Worktree Setup node — clone repos and create feature branch worktrees."""

from __future__ import annotations

from langgraph.types import RunnableConfig

import logging
from typing import Any

from hadron.git.worktree import WorktreeManager
from hadron.models.events import EventType, PipelineEvent
from hadron.models.pipeline_state import PipelineState

logger = logging.getLogger(__name__)


async def worktree_setup_node(state: PipelineState, config: RunnableConfig) -> dict[str, Any]:
    """Clone repos and set up worktrees for the CR."""
    configurable = config.get("configurable", {})
    event_bus = configurable.get("event_bus")
    workspace_dir = configurable.get("workspace_dir", "/tmp/hadron-workspace")
    cr_id = state["cr_id"]

    if event_bus:
        await event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_ENTERED, stage="worktree_setup"
        ))

    wm = WorktreeManager(workspace_dir)
    repos = state.get("affected_repos", [])
    updated_repos = []

    for repo in repos:
        repo_url = repo["repo_url"]
        repo_name = repo.get("repo_name", repo_url.rstrip("/").split("/")[-1])
        default_branch = repo.get("default_branch", "main")

        logger.info("Setting up worktree for %s (CR %s)", repo_name, cr_id)

        await wm.clone_bare(repo_url, repo_name)
        worktree_path = await wm.create_worktree(repo_name, cr_id, default_branch)

        # Read AGENTS.md if it exists
        agents_md = ""
        for agents_file in ["AGENTS.md", "CLAUDE.md"]:
            agents_path = worktree_path / agents_file
            if agents_path.exists():
                agents_md = agents_path.read_text()
                break

        dir_tree = await wm.get_directory_tree(worktree_path)

        updated_repos.append({
            **repo,
            "repo_name": repo_name,
            "worktree_path": str(worktree_path),
            "agents_md": agents_md,
        })

    if event_bus:
        await event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_COMPLETED, stage="worktree_setup",
            data={"worktrees": [r["worktree_path"] for r in updated_repos]},
        ))

    return {
        "affected_repos": updated_repos,
        "current_stage": "worktree_setup",
        "stage_history": [{"stage": "worktree_setup", "status": "completed"}],
    }
