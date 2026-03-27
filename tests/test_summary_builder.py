"""Tests for hadron.observability.summary."""

from __future__ import annotations

import pytest

from hadron.observability.summary import build_run_summary


def _make_state(**overrides):
    """Build a minimal PipelineState dict with defaults."""
    state = {
        "status": "completed",
        "cost_usd": 1.5,
        "cost_input_tokens": 10000,
        "cost_output_tokens": 5000,
        "stage_history": [],
        "verification_loop_count": 1,
        "dev_loop_count": 1,
        "review_loop_count": 1,
        "throttle_count": 0,
        "throttle_seconds": 0.0,
    }
    state.update(overrides)
    return state


class TestBuildRunSummary:
    def test_basic_success(self):
        state = _make_state(
            stage_history=[
                {"stage": "intake", "status": "completed", "entered_at": 1000.0, "completed_at": 1010.0},
                {"stage": "implementation", "status": "completed", "entered_at": 1010.0, "completed_at": 1060.0},
                {"stage": "review", "status": "completed", "entered_at": 1060.0, "completed_at": 1080.0},
                {"stage": "release", "status": "completed", "entered_at": 1080.0, "completed_at": 1090.0},
            ],
        )
        summary = build_run_summary("CR-001", "my-repo", state)

        assert summary["cr_id"] == "CR-001"
        assert summary["repo_name"] == "my-repo"
        assert summary["final_status"] == "completed"
        assert summary["error_category"] is None
        assert summary["duration_seconds"] == 90.0
        assert summary["total_cost_usd"] == 1.5
        assert summary["total_input_tokens"] == 10000
        assert summary["total_output_tokens"] == 5000

    def test_stage_timings(self):
        state = _make_state(
            stage_history=[
                {"stage": "intake", "status": "completed", "entered_at": 100.0, "completed_at": 110.0},
                {"stage": "implementation", "status": "completed", "entered_at": 110.0, "completed_at": 160.0},
            ],
        )
        summary = build_run_summary("CR-001", "repo", state)

        timings = summary["stage_timings"]
        assert "intake" in timings
        assert timings["intake"]["duration_s"] == 10.0
        assert "implementation" in timings
        assert timings["implementation"]["duration_s"] == 50.0

    def test_repeated_stages_numbered(self):
        state = _make_state(
            stage_history=[
                {"stage": "implementation", "status": "completed", "entered_at": 100.0, "completed_at": 150.0},
                {"stage": "review", "status": "completed", "entered_at": 150.0, "completed_at": 160.0},
                {"stage": "implementation", "status": "completed", "entered_at": 160.0, "completed_at": 200.0},
            ],
        )
        summary = build_run_summary("CR-001", "repo", state)

        timings = summary["stage_timings"]
        assert "implementation" in timings
        assert "implementation_2" in timings
        assert timings["implementation_2"]["stage"] == "implementation"

    def test_missing_timestamps_handled(self):
        state = _make_state(
            stage_history=[
                {"stage": "intake", "status": "completed"},
            ],
        )
        summary = build_run_summary("CR-001", "repo", state)

        assert summary["duration_seconds"] == 0.0
        assert summary["started_at"] is None
        assert summary["completed_at"] is None
        timings = summary["stage_timings"]
        assert timings["intake"]["duration_s"] is None

    def test_review_findings_summary(self):
        state = _make_state(
            review_results=[
                {
                    "review_iteration": 1,
                    "review_passed": False,
                    "findings": [
                        {"severity": "critical", "message": "SQL injection"},
                        {"severity": "major", "message": "No input validation"},
                        {"severity": "minor", "message": "Style issue"},
                    ],
                },
                {
                    "review_iteration": 2,
                    "review_passed": True,
                    "findings": [
                        {"severity": "minor", "message": "Style issue"},
                    ],
                },
            ],
        )
        summary = build_run_summary("CR-001", "repo", state)

        rfs = summary["review_findings_summary"]
        assert rfs is not None
        assert len(rfs["iterations"]) == 2
        assert rfs["iterations"][0]["critical"] == 1
        assert rfs["iterations"][0]["major"] == 1
        assert rfs["iterations"][0]["passed"] is False
        assert rfs["iterations"][1]["passed"] is True
        assert rfs["total_findings"] == 4
        assert rfs["final_passed"] is True

    def test_no_review_results(self):
        state = _make_state()
        summary = build_run_summary("CR-001", "repo", state)
        assert summary["review_findings_summary"] is None

    def test_failure_state(self):
        state = _make_state(
            status="failed",
            error="Something crashed",
        )
        summary = build_run_summary("CR-001", "repo", state)
        assert summary["final_status"] == "failed"
        assert summary["error_category"] == "agent_crash"
        assert summary["error_message"] == "Something crashed"

    def test_paused_budget(self):
        state = _make_state(
            status="paused",
            pause_reason="budget_exceeded",
            cost_usd=10.5,
        )
        summary = build_run_summary("CR-001", "repo", state)
        assert summary["final_status"] == "paused"
        assert summary["error_category"] == "budget_exceeded"
        assert summary["pause_reason"] == "budget_exceeded"

    def test_model_breakdown_passed_through(self):
        breakdown = {"claude-sonnet-4-6": {"cost_usd": 1.0, "input_tokens": 5000}}
        state = _make_state(model_breakdown=breakdown)
        summary = build_run_summary("CR-001", "repo", state)
        assert summary["model_breakdown"] == breakdown

    def test_empty_state(self):
        summary = build_run_summary("CR-001", "repo", {})
        assert summary["cr_id"] == "CR-001"
        assert summary["final_status"] == "completed"
        assert summary["duration_seconds"] == 0.0
