"""Classify pipeline errors into structured categories."""

from __future__ import annotations

import re
from typing import Any

# Patterns matched against the error string (case-insensitive)
_API_ERROR_PATTERNS = re.compile(
    r"(api\s*error|rate\s*limit|overloaded|503|529|timeout|connection\s*(refused|reset|error))",
    re.IGNORECASE,
)
_TEST_FAILURE_PATTERNS = re.compile(
    r"(test.*fail|tests?\s+did\s+not\s+pass|pytest|vitest|jest|npm\s+test)",
    re.IGNORECASE,
)


def classify_error(final_state: dict[str, Any]) -> str | None:
    """Classify a pipeline error into a category based on pause_reason and error text.

    Returns None for successful runs with no error.
    """
    status = final_state.get("status", "")
    if status == "completed":
        return None

    pause_reason = final_state.get("pause_reason") or ""
    error = final_state.get("error") or ""

    if pause_reason == "budget_exceeded":
        return "budget_exceeded"

    if pause_reason == "rebase_conflict":
        return "rebase_conflict"

    if pause_reason == "circuit_breaker":
        review_loop = final_state.get("review_loop_count", 0)
        verification_loop = final_state.get("verification_loop_count", 0)
        config = final_state.get("config_snapshot", {}).get("pipeline", {})
        if review_loop >= config.get("max_review_dev_loops", 3):
            return "review_circuit_breaker"
        if verification_loop >= config.get("max_verification_loops", 3):
            return "verification_circuit_breaker"
        return "circuit_breaker"

    if _API_ERROR_PATTERNS.search(error):
        return "api_error"

    if _TEST_FAILURE_PATTERNS.search(error):
        return "test_failure"

    if error:
        return "agent_crash"

    return "unknown"
