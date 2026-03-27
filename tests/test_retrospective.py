"""Tests for hadron.observability.retrospective."""

from __future__ import annotations

import pytest

from hadron.observability.retrospective import generate_retrospective


def _make_summary(**overrides):
    """Build a minimal RunSummary dict with defaults."""
    summary = {
        "final_status": "completed",
        "verification_loop_count": 1,
        "dev_loop_count": 1,
        "review_loop_count": 1,
        "error_category": None,
        "throttle_seconds": 0.0,
        "total_cost_usd": 1.0,
        "duration_seconds": 60.0,
        "stage_timings": {},
        "review_findings_summary": None,
    }
    summary.update(overrides)
    return summary


class TestCleanPass:
    def test_first_pass_completion(self):
        insights = generate_retrospective(_make_summary())
        assert len(insights) == 1
        assert insights[0]["title"] == "Clean first-pass completion"
        assert insights[0]["severity"] == "info"

    def test_clean_pass_returns_early(self):
        """Clean pass should not generate any other insights."""
        insights = generate_retrospective(_make_summary())
        assert all(i["category"] == "efficiency" for i in insights)


class TestSpecLooping:
    def test_verification_loops_warning(self):
        insights = generate_retrospective(_make_summary(
            verification_loop_count=2,
        ))
        titles = [i["title"] for i in insights]
        assert "Spec translation required multiple iterations" in titles

    def test_single_verification_no_warning(self):
        insights = generate_retrospective(_make_summary(
            verification_loop_count=1,
        ))
        titles = [i["title"] for i in insights]
        assert "Spec translation required multiple iterations" not in titles


class TestReviewCycling:
    def test_excessive_review_warning(self):
        insights = generate_retrospective(_make_summary(review_loop_count=3))
        titles = [i["title"] for i in insights]
        assert "Excessive review/rework cycling" in titles

    def test_two_reviews_no_warning(self):
        insights = generate_retrospective(_make_summary(review_loop_count=2))
        titles = [i["title"] for i in insights]
        assert "Excessive review/rework cycling" not in titles


class TestStallDetection:
    def test_non_decreasing_findings(self):
        insights = generate_retrospective(_make_summary(
            review_loop_count=2,
            review_findings_summary={
                "iterations": [
                    {"critical": 2, "major": 1, "minor": 0, "info": 0, "passed": False},
                    {"critical": 2, "major": 1, "minor": 0, "info": 0, "passed": False},
                ],
            },
        ))
        titles = [i["title"] for i in insights]
        assert "Rework did not reduce blocking findings" in titles

    def test_decreasing_findings_no_warning(self):
        insights = generate_retrospective(_make_summary(
            review_loop_count=2,
            review_findings_summary={
                "iterations": [
                    {"critical": 3, "major": 2, "minor": 0, "info": 0, "passed": False},
                    {"critical": 1, "major": 0, "minor": 0, "info": 0, "passed": True},
                ],
            },
        ))
        titles = [i["title"] for i in insights]
        assert "Rework did not reduce blocking findings" not in titles

    def test_single_iteration_no_stall(self):
        insights = generate_retrospective(_make_summary(
            review_findings_summary={
                "iterations": [
                    {"critical": 5, "major": 0, "minor": 0, "info": 0, "passed": False},
                ],
            },
        ))
        titles = [i["title"] for i in insights]
        assert "Rework did not reduce blocking findings" not in titles


class TestCostBottleneck:
    def test_dominant_stage(self):
        insights = generate_retrospective(_make_summary(
            dev_loop_count=2,
            stage_timings={
                "intake": {"stage": "intake", "duration_s": 10.0},
                "implementation": {"stage": "implementation", "duration_s": 100.0},
                "review": {"stage": "review", "duration_s": 20.0},
            },
            total_cost_usd=5.0,
        ))
        titles = [i["title"] for i in insights]
        assert any("dominated pipeline time" in t for t in titles)

    def test_balanced_stages_no_bottleneck(self):
        insights = generate_retrospective(_make_summary(
            dev_loop_count=2,
            stage_timings={
                "intake": {"stage": "intake", "duration_s": 30.0},
                "implementation": {"stage": "implementation", "duration_s": 30.0},
                "review": {"stage": "review", "duration_s": 30.0},
            },
            total_cost_usd=5.0,
        ))
        titles = [i["title"] for i in insights]
        assert not any("dominated pipeline time" in t for t in titles)


class TestThrottling:
    def test_high_throttle_warning(self):
        insights = generate_retrospective(_make_summary(throttle_seconds=120.0, dev_loop_count=2))
        titles = [i["title"] for i in insights]
        assert "Significant API rate limiting" in titles

    def test_low_throttle_no_warning(self):
        insights = generate_retrospective(_make_summary(throttle_seconds=30.0, dev_loop_count=2))
        titles = [i["title"] for i in insights]
        assert "Significant API rate limiting" not in titles


class TestBudgetExceeded:
    def test_budget_exceeded_critical(self):
        insights = generate_retrospective(_make_summary(
            final_status="paused",
            error_category="budget_exceeded",
            total_cost_usd=10.5,
        ))
        budget_insight = [i for i in insights if "budget" in i["title"].lower()]
        assert len(budget_insight) == 1
        assert budget_insight[0]["severity"] == "critical"


class TestCircuitBreaker:
    def test_review_circuit_breaker(self):
        insights = generate_retrospective(_make_summary(
            final_status="paused",
            error_category="review_circuit_breaker",
            review_loop_count=3,
        ))
        titles = [i["title"] for i in insights]
        assert any("circuit breaker" in t.lower() for t in titles)

    def test_verification_circuit_breaker(self):
        insights = generate_retrospective(_make_summary(
            final_status="paused",
            error_category="verification_circuit_breaker",
            verification_loop_count=3,
        ))
        titles = [i["title"] for i in insights]
        assert any("circuit breaker" in t.lower() for t in titles)


class TestAgentCrash:
    def test_agent_crash_insight(self):
        insights = generate_retrospective(_make_summary(
            final_status="failed",
            error_category="agent_crash",
            error_message="KeyError: 'missing'",
        ))
        titles = [i["title"] for i in insights]
        assert "Pipeline failed: agent crash" in titles


class TestApiError:
    def test_api_error_insight(self):
        insights = generate_retrospective(_make_summary(
            final_status="failed",
            error_category="api_error",
            error_message="APIError: 503",
        ))
        titles = [i["title"] for i in insights]
        assert "Pipeline failed: API error" in titles


class TestMultipleDevIterations:
    def test_many_dev_iterations(self):
        insights = generate_retrospective(_make_summary(dev_loop_count=3))
        titles = [i["title"] for i in insights]
        assert "Multiple implementation iterations" in titles

    def test_few_dev_iterations_no_insight(self):
        insights = generate_retrospective(_make_summary(dev_loop_count=2))
        titles = [i["title"] for i in insights]
        assert "Multiple implementation iterations" not in titles
