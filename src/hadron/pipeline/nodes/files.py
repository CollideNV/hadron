"""File gathering utilities for pipeline nodes."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from hadron.config.limits import MAX_CONTEXT_CHARS

logger = logging.getLogger(__name__)


def gather_files(worktree: str, pattern: str) -> str:
    """Read files matching glob pattern and return formatted content."""
    base = Path(worktree)
    parts: list[str] = []
    total = 0
    for path in sorted(base.glob(pattern)):
        if not path.is_file():
            continue
        content = path.read_text(errors="replace")
        rel = path.relative_to(base)
        entry = f"### {rel}\n\n```\n{content}\n```"
        if total + len(entry) > MAX_CONTEXT_CHARS:
            parts.append(f"\n... ({pattern}: remaining files truncated)")
            break
        parts.append(entry)
        total += len(entry)
    return "\n\n".join(parts)


def _get_changed_file_set(worktree: str, default_branch: str = "main") -> set[str]:
    """Return the set of changed/added/untracked file paths relative to worktree root.

    Runs git merge-base, git diff, and git ls-files once. Multiple callers
    needing different glob patterns can share this result.
    """
    import subprocess

    changed: set[str] = set()

    def _lines(result: subprocess.CompletedProcess[str]) -> list[str]:
        return [l.strip() for l in result.stdout.splitlines() if l.strip()]

    try:
        merge_base = subprocess.run(
            ["git", "merge-base", default_branch, "HEAD"],
            cwd=worktree, capture_output=True, text=True, timeout=10,
        )
        if merge_base.returncode == 0 and merge_base.stdout.strip():
            committed = subprocess.run(
                ["git", "diff", "--name-only", "--diff-filter=ACMR",
                 merge_base.stdout.strip(), "HEAD"],
                cwd=worktree, capture_output=True, text=True, timeout=10,
            )
            changed.update(_lines(committed))

        uncommitted = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=ACMR", "HEAD"],
            cwd=worktree, capture_output=True, text=True, timeout=10,
        )
        changed.update(_lines(uncommitted))

        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=worktree, capture_output=True, text=True, timeout=10,
        )
        changed.update(_lines(untracked))

    except (subprocess.SubprocessError, OSError) as exc:
        logger.warning("git commands failed in _get_changed_file_set: %s", exc)

    return changed


def _read_matched_files(worktree: str, pattern: str, changed: set[str]) -> str:
    """Read files matching glob pattern from the changed set."""
    base = Path(worktree)

    if not changed:
        return ""

    matching = {str(p.relative_to(base)) for p in base.glob(pattern) if p.is_file()}
    matched = sorted(changed & matching)

    if not matched:
        return ""

    parts: list[str] = []
    total = 0
    for rel in matched:
        path = base / rel
        if not path.is_file():
            continue
        content = path.read_text(errors="replace")
        entry = f"### {rel}\n\n```\n{content}\n```"
        if total + len(entry) > MAX_CONTEXT_CHARS:
            parts.append(f"\n... ({pattern}: remaining files truncated)")
            break
        parts.append(entry)
        total += len(entry)
    return "\n\n".join(parts)


def gather_changed_files(worktree: str, pattern: str, default_branch: str = "main") -> str:
    """Read files matching glob pattern that were added or modified in this branch."""
    changed = _get_changed_file_set(worktree, default_branch)
    return _read_matched_files(worktree, pattern, changed)


def gather_changed_files_multi(
    worktree: str,
    patterns: list[str],
    default_branch: str = "main",
) -> dict[str, str]:
    """Like gather_changed_files but for multiple patterns with a single git call.

    Returns a dict mapping each pattern to its gathered content string.
    """
    changed = _get_changed_file_set(worktree, default_branch)
    return {pattern: _read_matched_files(worktree, pattern, changed) for pattern in patterns}
