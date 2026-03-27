"""Rule-based retrospective engine — produces actionable insights from a RunSummary."""

from __future__ import annotations

from typing import Any


def _insight(
    category: str, severity: str, title: str, detail: str,
    suggestion: str = "", metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "category": category,
        "severity": severity,
        "title": title,
        "detail": detail,
        "suggestion": suggestion,
        "metrics": metrics or {},
    }


def generate_retrospective(summary: dict[str, Any]) -> list[dict[str, Any]]:
    """Produce insights from a RunSummary dict. Returns list of insight dicts."""
    insights: list[dict[str, Any]] = []

    status = summary.get("final_status", "")
    verification_loops = summary.get("verification_loop_count", 0)
    dev_loops = summary.get("dev_loop_count", 0)
    review_loops = summary.get("review_loop_count", 0)
    error_category = summary.get("error_category")
    throttle_seconds = summary.get("throttle_seconds", 0.0)
    total_cost = summary.get("total_cost_usd", 0.0)
    duration = summary.get("duration_seconds", 0.0)
    stage_timings = summary.get("stage_timings") or {}
    review_summary = summary.get("review_findings_summary") or {}

    # --- Clean pass ---
    if (
        status == "completed"
        and verification_loops <= 1
        and review_loops <= 1
        and dev_loops <= 1
    ):
        insights.append(_insight(
            "efficiency", "info",
            "Clean first-pass completion",
            "Pipeline completed on the first attempt with no rework loops.",
            metrics={"duration_s": duration, "cost_usd": total_cost},
        ))
        return insights  # No issues to report

    # --- Spec translation looping ---
    if verification_loops > 1:
        insights.append(_insight(
            "efficiency", "warning",
            "Spec translation required multiple iterations",
            f"The behaviour translation/verification loop ran {verification_loops} "
            f"times before producing accepted specs.",
            suggestion="Review the translation prompt or spec template. "
            "Repeated verification failures may indicate ambiguous CR descriptions.",
            metrics={"verification_loop_count": verification_loops},
        ))

    # --- Review cycling ---
    if review_loops > 2:
        insights.append(_insight(
            "quality", "warning",
            "Excessive review/rework cycling",
            f"The review/rework loop ran {review_loops} times. "
            f"This increases cost and duration significantly.",
            suggestion="Check if the implementation prompt is missing context that "
            "reviewers consistently flag. Consider making review criteria "
            "visible to the implementation agent.",
            metrics={"review_loop_count": review_loops},
        ))

    # --- Stall detection (non-decreasing finding counts) ---
    iterations = review_summary.get("iterations", [])
    if len(iterations) >= 2:
        blocking_counts = [
            it.get("critical", 0) + it.get("major", 0) for it in iterations
        ]
        stalled = all(
            blocking_counts[i] >= blocking_counts[i - 1]
            for i in range(1, len(blocking_counts))
        )
        if stalled and len(blocking_counts) >= 2 and blocking_counts[-1] > 0:
            insights.append(_insight(
                "quality", "warning",
                "Rework did not reduce blocking findings",
                f"Blocking finding counts across review iterations: {blocking_counts}. "
                "Rework was not making progress.",
                suggestion="This pattern often means the rework agent is introducing "
                "new issues while fixing old ones. Consider a fresh implementation "
                "approach for similar CRs.",
                metrics={"finding_counts": blocking_counts},
            ))

    # --- Cost bottleneck (single stage > 50% of cost) ---
    if stage_timings and total_cost > 0:
        total_dur = sum(
            (info.get("duration_s") or 0) for info in stage_timings.values()
        )
        if total_dur > 0:
            for key, info in stage_timings.items():
                dur = info.get("duration_s") or 0
                fraction = dur / total_dur
                if fraction > 0.5:
                    stage_name = info.get("stage", key)
                    insights.append(_insight(
                        "cost", "info",
                        f"Stage '{stage_name}' dominated pipeline time",
                        f"This stage consumed {fraction:.0%} of total pipeline duration "
                        f"({dur:.0f}s out of {total_dur:.0f}s).",
                        suggestion=f"Investigate why '{stage_name}' takes disproportionately "
                        "long. This may be normal for complex CRs or indicate an issue.",
                        metrics={
                            "stage": stage_name,
                            "duration_s": dur,
                            "fraction": round(fraction, 3),
                        },
                    ))
                    break  # Only report the top bottleneck

    # --- Throttling impact ---
    if throttle_seconds > 60:
        insights.append(_insight(
            "cost", "warning",
            "Significant API rate limiting",
            f"The pipeline spent {throttle_seconds:.0f}s waiting on API rate limits.",
            suggestion="Consider distributing load across models or adjusting "
            "concurrency settings to reduce throttling.",
            metrics={"throttle_seconds": throttle_seconds},
        ))

    # --- Budget exceeded ---
    if error_category == "budget_exceeded":
        insights.append(_insight(
            "cost", "critical",
            "Pipeline paused: budget exceeded",
            f"Cost reached ${total_cost:.4f} and hit the configured budget limit.",
            suggestion="Consider increasing the budget for complex CRs, "
            "or investigate which stage consumed the most cost.",
            metrics={"total_cost_usd": total_cost},
        ))

    # --- Circuit breaker ---
    if error_category in ("review_circuit_breaker", "verification_circuit_breaker"):
        loop_type = "review/rework" if "review" in error_category else "verification"
        insights.append(_insight(
            "quality", "critical",
            f"Circuit breaker tripped: {loop_type} loop limit reached",
            f"The {loop_type} loop hit its maximum iteration limit without converging.",
            suggestion=f"The {loop_type} process is not converging. "
            "Review the prompts and consider whether this type of CR "
            "needs different handling.",
            metrics={"error_category": error_category},
        ))

    # --- Rebase conflict ---
    if error_category == "rebase_conflict":
        insights.append(_insight(
            "failure", "warning",
            "Pipeline paused: rebase conflict",
            "The rebase stage encountered merge conflicts that could not "
            "be automatically resolved.",
            suggestion="This typically indicates the target branch changed "
            "significantly during pipeline execution. Consider running CRs "
            "against a more stable base or reducing pipeline duration.",
        ))

    # --- Agent crash ---
    if error_category == "agent_crash":
        error_msg = summary.get("error_message", "")
        insights.append(_insight(
            "failure", "critical",
            "Pipeline failed: agent crash",
            f"An agent encountered an unhandled error: {error_msg[:200]}",
            suggestion="Check the error details and worker logs for the root cause.",
            metrics={"error_message": error_msg[:500]},
        ))

    # --- API error ---
    if error_category == "api_error":
        insights.append(_insight(
            "failure", "critical",
            "Pipeline failed: API error",
            f"An API call failed: {summary.get('error_message', '')[:200]}",
            suggestion="This may be a transient issue. Consider resuming the pipeline.",
            metrics={"error_message": summary.get("error_message", "")[:500]},
        ))

    # --- Multiple dev iterations ---
    if dev_loops > 2:
        insights.append(_insight(
            "efficiency", "info",
            "Multiple implementation iterations",
            f"The implementation agent ran {dev_loops} iterations (including rework restarts).",
            metrics={"dev_loop_count": dev_loops},
        ))

    return insights
