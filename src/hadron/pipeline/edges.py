"""Conditional edge functions for the pipeline graph."""

from __future__ import annotations

from hadron.models.pipeline_state import PipelineState


def after_verification(state: PipelineState) -> str:
    """Route after behaviour verification.

    Returns:
        "translation" — specs rejected, loop back (within circuit breaker)
        "tdd" — specs verified, proceed
        "paused" — circuit breaker tripped
    """
    if state.get("behaviour_verified"):
        return "tdd"

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
        "tdd" — review failed, loop back (within circuit breaker)
        "paused" — circuit breaker tripped
    """
    if state.get("review_passed"):
        return "rebase"

    max_loops = (
        state.get("config_snapshot", {})
        .get("pipeline", {})
        .get("max_review_dev_loops", 3)
    )
    if state.get("review_loop_count", 0) >= max_loops:
        return "paused"

    return "tdd"


def after_rebase(state: PipelineState) -> str:
    """Route after rebase.

    Returns:
        "delivery" — rebase clean (or conflicts resolved by agent)
        "paused" — unresolvable conflicts
    """
    if state.get("rebase_clean", True):
        return "delivery"
    return "paused"
