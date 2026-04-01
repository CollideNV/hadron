"""Worktree Setup node — clone repo and create feature branch worktree.

Each worker handles exactly one repo. This node clones the repo,
creates a worktree, installs dependencies, reads AGENTS.md/CLAUDE.md,
and auto-detects languages and test commands from marker files.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

from hadron.git.detect import detect_e2e_tests, detect_languages_and_tests
from hadron.git.url import extract_repo_name
from hadron.models.events import EventType, PipelineEvent
from hadron.models.pipeline_state import PipelineState
from hadron.pipeline.nodes import NodeContext, pipeline_node

logger = logging.getLogger(__name__)


async def _install_dependencies(worktree_path: Path) -> None:
    """Install project dependencies if lock files are present.

    In subprocess mode (local dev), the worker shares the controller's venv.
    Using ``pip install -e`` would hijack the editable install to point at
    the worktree instead of the main repo, and a plain ``pip install`` creates
    a static copy that won't reflect the agent's edits. So we skip Python
    deps when the package is already importable. In K8s mode each pod has
    its own environment and ``pip install -e`` is safe.
    """
    # Each entry: (label, command, working_directory)
    installs: list[tuple[str, list[str], str]] = []
    root = str(worktree_path)

    # Python — only install if the package isn't already available
    if (worktree_path / "pyproject.toml").exists() or (worktree_path / "requirements.txt").exists():
        # Detect the package name from pyproject.toml or directory
        pkg_name = worktree_path.name  # fallback
        pyproject = worktree_path / "pyproject.toml"
        if pyproject.exists():
            try:
                import tomllib
                data = tomllib.loads(pyproject.read_text())
                pkg_name = data.get("project", {}).get("name", pkg_name)
            except Exception:
                pass

        # Check if the package is already importable (subprocess mode sharing venv)
        already_installed = False
        try:
            __import__(pkg_name.replace("-", "_"))
            already_installed = True
        except ImportError:
            pass

        if already_installed:
            logger.info("Python package %r already installed — skipping pip install", pkg_name)
        elif (worktree_path / "pyproject.toml").exists():
            installs.append(("python", [sys.executable, "-m", "pip", "install", "-e", ".[dev]", "--quiet"], root))
        else:
            installs.append(("python", [sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "--quiet"], root))

    # Node — check root and common subdirs; use cwd (not --prefix) to avoid lockfile sync issues
    for subdir in [".", "frontend", "client", "web", "app"]:
        pkg = worktree_path / subdir / "package.json"
        if pkg.exists():
            lock = worktree_path / subdir / "package-lock.json"
            npm_cwd = str(worktree_path / subdir)
            cmd = ["npm", "ci"] if lock.exists() else ["npm", "install"]
            installs.append((f"node ({subdir})", cmd, npm_cwd))

    for label, cmd, install_cwd in installs:
        logger.info("Installing %s dependencies: %s (in %s)", label, " ".join(cmd), install_cwd)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=install_cwd,
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

    # Auto-detect E2E test commands (AGENTS.md overrides marker files)
    e2e_test_commands = detect_e2e_tests(
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
        "e2e_test_commands": e2e_test_commands,
    }

    await ctx.event_bus.emit(PipelineEvent(
        cr_id=cr_id, event_type=EventType.STAGE_COMPLETED, stage="worktree_setup",
        data={
            "worktree_path": str(worktree_path),
            "languages": languages,
            "test_commands": test_commands,
            "e2e_test_commands": e2e_test_commands,
        },
    ))

    return {
        "repo": updated_repo,
        "directory_tree": dir_tree,
        "current_stage": "worktree_setup",
        "stage_history": [{"stage": "worktree_setup", "status": "completed"}],
    }
