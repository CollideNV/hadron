"""Utilities for discovering per-worktree virtual environments."""

from __future__ import annotations

import os
from pathlib import Path


def find_worktree_venv(directory: str) -> str | None:
    """Walk up from *directory* to find a worktree ``.venv/bin`` directory.

    Checks *directory* itself and every parent up to the filesystem root.
    Returns the ``.venv`` path (not ``bin/``) or ``None``.
    """
    current = Path(directory).resolve()
    for _ in range(20):  # safety limit
        candidate = current / ".venv" / "bin"
        if candidate.is_dir():
            return str(current / ".venv")
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def worktree_env(worktree_path: str, base_env: dict[str, str] | None = None) -> dict[str, str]:
    """Build an env dict that activates the worktree venv if present.

    Prepends ``.venv/bin`` to PATH, sets VIRTUAL_ENV, and adds
    ``node_modules/.bin`` directories for npm scripts.
    """
    env = dict(base_env) if base_env is not None else dict(os.environ)
    venv_path = find_worktree_venv(worktree_path)
    if venv_path:
        venv_bin = os.path.join(venv_path, "bin")
        env["PATH"] = venv_bin + os.pathsep + env.get("PATH", "")
        env["VIRTUAL_ENV"] = venv_path
    return env
