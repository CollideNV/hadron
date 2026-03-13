"""Resume logic — shared between Controller and Worker."""

from __future__ import annotations

# Maps override keys to the pipeline node they logically belong to.
# When resuming with overrides, the latest node in pipeline order is used as as_node.
OVERRIDE_NODE_MAP: dict[str, str] = {
    "rebase_clean": "rebase",
    "review_passed": "review",
    "behaviour_verified": "verification",
}

# Pipeline node execution order (used to pick the latest node from multiple overrides).
PIPELINE_NODE_ORDER: list[str] = [
    "intake", "repo_id", "worktree_setup", "translation", "verification",
    "implementation", "review", "rebase", "delivery", "release",
]


def pick_resume_node(overrides: dict) -> str:
    """Pick the latest pipeline node that corresponds to the given overrides."""
    nodes = [OVERRIDE_NODE_MAP[k] for k in overrides if k in OVERRIDE_NODE_MAP]
    if not nodes:
        return "paused"
    return max(nodes, key=lambda n: PIPELINE_NODE_ORDER.index(n) if n in PIPELINE_NODE_ORDER else -1)
