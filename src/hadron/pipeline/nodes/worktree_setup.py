"""Worktree Setup node — clone repo and create feature branch worktree.

Each worker handles exactly one repo. This node clones the repo,
creates a worktree, installs dependencies, reads AGENTS.md/CLAUDE.md,
and auto-detects languages and test commands from marker files.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from hadron.git.detect import detect_languages_and_tests
from hadron.git.url import extract_repo_name
from hadron.models.events import EventType, PipelineEvent
from hadron.models.pipeline_state import PipelineState
from hadron.pipeline.nodes import NodeContext, pipeline_node

logger = logging.getLogger(__name__)


async def _install_dependencies(worktree_path: Path) -> None:
    """Install project dependencies if lock files are present."""
    installs: list[tuple[str, list[str]]] = []

    # Python
    if (worktree_path / "pyproject.toml").exists() or (worktree_path / "requirements.txt").exists():
        if (worktree_path / "pyproject.toml").exists():
            installs.append(("python", ["pip", "install", "-e", ".[dev]", "--quiet"]))
        else:
            installs.append(("python", ["pip", "install", "-r", "requirements.txt", "--quiet"]))

    # Node — check root and common subdirs
    for subdir in [".", "frontend", "client", "web", "app"]:
        pkg = worktree_path / subdir / "package.json"
        if pkg.exists():
            lock = worktree_path / subdir / "package-lock.json"
            cmd = ["npm", "ci", "--prefix", str(worktree_path / subdir)] if lock.exists() else \
                  ["npm", "install", "--prefix", str(worktree_path / subdir)]
            installs.append((f"node ({subdir})", cmd))

    for label, cmd in installs:
        logger.info("Installing %s dependencies: %s", label, " ".join(cmd))
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(worktree_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=300)
        if proc.returncode != 0:
            logger.warning(
                "Dependency install failed for %s (exit %d): %s",
                label, proc.returncode, stdout.decode(errors="replace")[-500:],
            )
        else:
            logger.info("Installed %s dependencies successfully", label)


@pipeline_node("worktree_setup")
async def worktree_setup_node(state: PipelineState, ctx: NodeContext, cr_id: str) -> dict[str, Any]:
    """Clone repo and set up worktree for the CR."""
    wm = ctx.worktree_manager
    repo = state.get("repo", {})
    repo_url = repo["repo_url"]
    repo_name = repo.get("repo_name") or extract_repo_name(repo_url)
    default_branch = repo.get("default_branch", "main")

    logger.info("Setting up worktree for %s (CR %s)", repo_name, cr_id)

    await wm.clone_bare(repo_url, repo_name)
    worktree_path = await wm.create_worktree(repo_name, cr_id, default_branch)

    # Read AGENTS.md / CLAUDE.md if present
    agents_md = ""
    for agents_file in ["AGENTS.md", "CLAUDE.md"]:
        agents_path = worktree_path / agents_file
        if agents_path.exists():
            agents_md = agents_path.read_text()
            break

    # Install dependencies before detection (so test commands work)
    await _install_dependencies(worktree_path)

    # Auto-detect languages and test commands (AGENTS.md overrides marker files)
    languages, test_commands = detect_languages_and_tests(
        str(worktree_path), agents_md=agents_md,
    )

    dir_tree = await wm.get_directory_tree(worktree_path)

    updated_repo = {
        **repo,
        "repo_name": repo_name,
        "worktree_path": str(worktree_path),
        "agents_md": agents_md,
        "languages": languages,
        "test_commands": test_commands,
    }

    await ctx.event_bus.emit(PipelineEvent(
        cr_id=cr_id, event_type=EventType.STAGE_COMPLETED, stage="worktree_setup",
        data={
            "worktree_path": str(worktree_path),
            "languages": languages,
            "test_commands": test_commands,
        },
    ))

    return {
        "repo": updated_repo,
        "directory_tree": dir_tree,
        "current_stage": "worktree_setup",
        "stage_history": [{"stage": "worktree_setup", "status": "completed"}],
    }
