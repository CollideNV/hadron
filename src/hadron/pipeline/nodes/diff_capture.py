"""Emit STAGE_DIFF events capturing what changed at each pipeline stage."""

from __future__ import annotations

import logging
import re

from hadron.config.limits import MAX_DIFF_EVENT_CHARS, MAX_FEATURE_CONTENT_EVENT_CHARS
from hadron.events.bus import EventBus
from hadron.git.worktree import WorktreeManager
from hadron.models.events import EventType, PipelineEvent

logger = logging.getLogger(__name__)


def _compute_diff_stats(diff: str) -> dict[str, int]:
    """Count files changed, insertions, and deletions from a unified diff."""
    files_changed = 0
    insertions = 0
    deletions = 0
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            files_changed += 1
        elif line.startswith("+") and not line.startswith("+++"):
            insertions += 1
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1
    return {
        "files_changed": files_changed,
        "insertions": insertions,
        "deletions": deletions,
    }


def _parse_feature_content(raw: str) -> list[dict[str, str]]:
    """Parse ``gather_changed_files`` markdown format into structured objects.

    Input format::

        ### path/to/file.feature

        ```
        file content
        ```

        ### another/file.feature
        ...

    Returns a list of ``{"path": ..., "content": ...}`` dicts.
    """
    if not raw.strip():
        return []

    files: list[dict[str, str]] = []
    # Split on ### headers
    parts = re.split(r"^### ", raw, flags=re.MULTILINE)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # First line is the path, rest contains ```...```
        lines = part.split("\n", 1)
        path = lines[0].strip()
        content = ""
        if len(lines) > 1:
            # Extract content between ``` markers
            match = re.search(r"```\n?(.*?)```", lines[1], re.DOTALL)
            if match:
                content = match.group(1).rstrip("\n")
        files.append({"path": path, "content": content})
    return files


async def emit_stage_diff(
    event_bus: EventBus,
    cr_id: str,
    stage: str,
    repo_name: str,
    worktree_manager: WorktreeManager,
    worktree_path: str,
    default_branch: str,
    feature_content: str = "",
) -> None:
    """Capture and emit a STAGE_DIFF event for the given stage.

    Parameters
    ----------
    feature_content:
        Raw markdown from ``gather_changed_files`` for .feature files.
        Will be parsed into structured ``[{path, content}]`` objects.
    """
    try:
        diff = await worktree_manager.get_diff(worktree_path, default_branch)
    except Exception as exc:
        logger.warning("Failed to get diff for stage %s: %s", stage, exc)
        diff = ""

    stats = _compute_diff_stats(diff)

    diff_truncated = len(diff) > MAX_DIFF_EVENT_CHARS
    if diff_truncated:
        diff = diff[:MAX_DIFF_EVENT_CHARS]

    # Parse feature files into structured format
    files: list[dict[str, str]] = []
    files_truncated = False
    if feature_content:
        files = _parse_feature_content(feature_content)
        # Truncate total content if needed
        total = sum(len(f["content"]) for f in files)
        if total > MAX_FEATURE_CONTENT_EVENT_CHARS:
            files_truncated = True
            budget = MAX_FEATURE_CONTENT_EVENT_CHARS
            for f in files:
                if budget <= 0:
                    f["content"] = "(truncated)"
                elif len(f["content"]) > budget:
                    f["content"] = f["content"][:budget] + "\n(truncated)"
                    budget = 0
                else:
                    budget -= len(f["content"])

    data: dict = {
        "repo": repo_name,
        "diff": diff,
        "diff_truncated": diff_truncated,
        "stats": stats,
    }
    if files:
        data["files"] = files
        data["files_truncated"] = files_truncated

    await event_bus.emit(PipelineEvent(
        cr_id=cr_id,
        event_type=EventType.STAGE_DIFF,
        stage=stage,
        data=data,
    ))
