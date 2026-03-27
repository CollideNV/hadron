"""Build a structured RunSummary from final PipelineState."""

from __future__ import annotations

import datetime
from typing import Any

from hadron.observability.error_classifier import classify_error


def _build_stage_timings(stage_history: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Extract per-stage timing from stage_history entries.

    If a stage appears multiple times (loops), entries are numbered:
    intake, implementation, implementation_2, etc.
    """
    timings: dict[str, dict[str, Any]] = {}
    seen: dict[str, int] = {}

    for entry in stage_history:
        stage = entry.get("stage", "unknown")
        seen[stage] = seen.get(stage, 0) + 1
        key = stage if seen[stage] == 1 else f"{stage}_{seen[stage]}"

        entered_at = entry.get("entered_at")
        completed_at = entry.get("completed_at")
        duration_s = (
            completed_at - entered_at
            if entered_at is not None and completed_at is not None
            else None
        )

        timings[key] = {
            "stage": stage,
            "status": entry.get("status", "completed"),
            "entered_at": entered_at,
            "completed_at": completed_at,
            "duration_s": round(duration_s, 3) if duration_s is not None else None,
        }

    return timings


def _build_review_findings_summary(
    review_results: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Summarise review findings across iterations."""
    if not review_results:
        return None

    iterations = []
    total_findings = 0
    final_passed = False

    for result in review_results:
        findings = result.get("findings", [])
        counts = {"critical": 0, "major": 0, "minor": 0, "info": 0}
        for f in findings:
            sev = f.get("severity", "info")
            counts[sev] = counts.get(sev, 0) + 1

        total_findings += len(findings)
        passed = result.get("review_passed", False)
        final_passed = passed

        iterations.append({
            "iteration": result.get("review_iteration", len(iterations) + 1),
            **counts,
            "passed": passed,
        })

    return {
        "iterations": iterations,
        "total_findings": total_findings,
        "final_passed": final_passed,
    }


def build_run_summary(
    cr_id: str, repo_name: str, final_state: dict[str, Any],
) -> dict[str, Any]:
    """Build a RunSummary dict from the final PipelineState.

    Returns a dict matching the RunSummary model columns (excluding id/created_at).
    """
    stage_history = final_state.get("stage_history", [])
    stage_timings = _build_stage_timings(stage_history)

    # Derive started_at / completed_at from stage_history
    started_at_ts = None
    completed_at_ts = None
    for entry in stage_history:
        ea = entry.get("entered_at")
        ca = entry.get("completed_at")
        if ea is not None and (started_at_ts is None or ea < started_at_ts):
            started_at_ts = ea
        if ca is not None and (completed_at_ts is None or ca > completed_at_ts):
            completed_at_ts = ca

    started_at = (
        datetime.datetime.fromtimestamp(started_at_ts, tz=datetime.timezone.utc)
        if started_at_ts is not None
        else None
    )
    completed_at = (
        datetime.datetime.fromtimestamp(completed_at_ts, tz=datetime.timezone.utc)
        if completed_at_ts is not None
        else None
    )
    duration_seconds = (
        completed_at_ts - started_at_ts
        if started_at_ts is not None and completed_at_ts is not None
        else 0.0
    )

    review_findings_summary = _build_review_findings_summary(
        final_state.get("review_results", [])
    )

    return {
        "cr_id": cr_id,
        "repo_name": repo_name,
        "final_status": final_state.get("status", "completed"),
        "pause_reason": final_state.get("pause_reason"),
        "error_category": classify_error(final_state),
        "error_message": final_state.get("error"),
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_seconds": round(duration_seconds, 3),
        "stage_timings": stage_timings,
        "total_cost_usd": final_state.get("cost_usd", 0.0),
        "total_input_tokens": final_state.get("cost_input_tokens", 0),
        "total_output_tokens": final_state.get("cost_output_tokens", 0),
        "model_breakdown": final_state.get("model_breakdown"),
        "verification_loop_count": final_state.get("verification_loop_count", 0),
        "dev_loop_count": final_state.get("dev_loop_count", 0),
        "review_loop_count": final_state.get("review_loop_count", 0),
        "review_findings_summary": review_findings_summary,
        "throttle_count": final_state.get("throttle_count", 0),
        "throttle_seconds": final_state.get("throttle_seconds", 0.0),
    }
