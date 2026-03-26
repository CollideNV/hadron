"""Conditional edge functions for the pipeline graph."""

from __future__ import annotations

from hadron.models.pipeline_state import PipelineState


def _budget_exceeded(state: PipelineState) -> bool:
    """Check whether the pipeline has exceeded its cost budget."""
    max_cost = (
        state.get("config_snapshot", {})
        .get("pipeline", {})
        .get("max_cost_usd", 10.0)
    )
    return state.get("cost_usd", 0.0) >= max_cost


def after_verification(state: PipelineState) -> str:
    """Route after behaviour verification.

    Returns:
        "translation" — specs rejected, loop back (within circuit breaker)
        "implementation" — specs verified, proceed
        "paused" — circuit breaker tripped or node errored
    """
    # Stop immediately if the node errored (e.g. API failure)
    if state.get("status") == "paused":
        return "paused"

    if _budget_exceeded(state):
        return "paused"

    if state.get("behaviour_verified"):
        return "implementation"

    max_loops = (
        state.get("config_snapshot", {})
        .get("pipeline", {})
        .get("max_verification_loops", 3)
    )
    if state.get("verification_loop_count", 0) >= max_loops:
        return "paused"

    return "translation"


def after_review(state: PipelineState) -> str:
    """Route after code review.

    Returns:
        "rebase" — review passed, proceed
        "rework" — review failed, loop back for targeted fixes (within circuit breaker)
        "paused" — circuit breaker tripped or node errored
    """
    # Stop immediately if the node errored (e.g. API failure)
    if state.get("status") == "paused":
        return "paused"

    if _budget_exceeded(state):
        return "paused"

    if state.get("review_passed"):
        return "rebase"

    max_loops = (
        state.get("config_snapshot", {})
        .get("pipeline", {})
        .get("max_review_dev_loops", 3)
    )
    if state.get("review_loop_count", 0) >= max_loops:
        return "paused"

    return "rework"


def _route_to_e2e_or_review(state: PipelineState) -> str:
    """Shared routing logic for post-implementation and post-rework.

    Returns:
        "e2e_testing" — repo has E2E tests configured
        "review" — no E2E tests, proceed to review
        "paused" — node errored or budget exceeded
    """
    if state.get("status") == "paused":
        return "paused"
    if _budget_exceeded(state):
        return "paused"
    if state.get("repo", {}).get("e2e_test_commands"):
        return "e2e_testing"
    return "review"


def after_implementation(state: PipelineState) -> str:
    """Route after implementation."""
    return _route_to_e2e_or_review(state)


def after_rework(state: PipelineState) -> str:
    """Route after rework."""
    return _route_to_e2e_or_review(state)


def after_rebase(state: PipelineState) -> str:
    """Route after rebase.

    Returns:
        "delivery" — rebase clean (or conflicts resolved by agent)
        "paused" — unresolvable conflicts
    """
    if state.get("rebase_clean", True):
        return "delivery"
    return "paused"
