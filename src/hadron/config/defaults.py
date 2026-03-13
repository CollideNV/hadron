"""Hardcoded MVP defaults for pipeline configuration.

In production these will come from the database (runtime config, §21).
For MVP, they're frozen here and snapshotted into PipelineState at intake.
"""

from __future__ import annotations

# Canonical constants — import these instead of hardcoding strings.
DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_EXPLORE_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_PLAN_MODEL = "claude-opus-4-6"
DEFAULT_WORKSPACE_DIR = "/tmp/hadron-workspace"
BRANCH_PREFIX = "ai/cr-"

PIPELINE_DEFAULTS: dict = {
    # Circuit breakers
    "max_verification_loops": 3,
    "max_review_dev_loops": 3,
    "max_tdd_iterations": 5,
    "max_cost_usd": 10.0,
    # Agent models (three-phase execution)
    "default_model": DEFAULT_MODEL,
    "explore_model": DEFAULT_EXPLORE_MODEL,
    "plan_model": DEFAULT_PLAN_MODEL,
    # Delivery
    "delivery_strategy": "self_contained",
    # Timeouts (seconds)
    "agent_timeout": 300,
    "test_timeout": 120,
}

REPO_DEFAULTS: dict = {
    "default_branch": "main",
    "test_command": "pytest",
    "language": "python",
}


def get_config_snapshot() -> dict:
    """Return a frozen snapshot of all config for a CR run."""
    return {
        "pipeline": {**PIPELINE_DEFAULTS},
        "repo": {**REPO_DEFAULTS},
    }
