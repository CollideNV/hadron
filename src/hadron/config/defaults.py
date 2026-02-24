"""Hardcoded MVP defaults for pipeline configuration.

In production these will come from the database (runtime config, §21).
For MVP, they're frozen here and snapshotted into PipelineState at intake.
"""

from __future__ import annotations

PIPELINE_DEFAULTS: dict = {
    # Circuit breakers
    "max_verification_loops": 3,
    "max_review_dev_loops": 3,
    "max_tdd_iterations": 5,
    "max_cost_usd": 10.0,
    # Agent model
    "default_model": "claude-sonnet-4-20250514",
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
