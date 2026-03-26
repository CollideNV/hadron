"""Tests for pipeline conditional edge functions."""

from __future__ import annotations

import pytest

from hadron.pipeline.edges import (
    _budget_exceeded,
    _rework_is_stalled,
    after_implementation,
    after_rebase,
    after_review,
    after_rework,
    after_verification,
)
from hadron.pipeline.graph import _infer_pause_reason


# ---------------------------------------------------------------------------
# after_verification
# ---------------------------------------------------------------------------


class TestAfterVerification:
    def test_verified_returns_implementation(self) -> None:
        state = {"behaviour_verified": True, "verification_loop_count": 0}
        assert after_verification(state) == "implementation"

    def test_not_verified_below_max_returns_translation(self) -> None:
        state = {"behaviour_verified": False, "verification_loop_count": 1}
        assert after_verification(state) == "translation"

    def test_not_verified_at_max_returns_paused(self) -> None:
        state = {"behaviour_verified": False, "verification_loop_count": 3}
        assert after_verification(state) == "paused"

    def test_not_verified_above_max_returns_paused(self) -> None:
        state = {"behaviour_verified": False, "verification_loop_count": 5}
        assert after_verification(state) == "paused"

    def test_missing_behaviour_verified_treated_as_falsy(self) -> None:
        state = {"verification_loop_count": 1}
        assert after_verification(state) == "translation"

    def test_missing_verification_loop_count_defaults_to_zero(self) -> None:
        state = {"behaviour_verified": False}
        assert after_verification(state) == "translation"

    def test_custom_max_verification_loops(self) -> None:
        state = {
            "behaviour_verified": False,
            "verification_loop_count": 2,
            "config_snapshot": {
                "pipeline": {"max_verification_loops": 2},
            },
        }
        assert after_verification(state) == "paused"

    def test_custom_max_not_reached(self) -> None:
        state = {
            "behaviour_verified": False,
            "verification_loop_count": 4,
            "config_snapshot": {
                "pipeline": {"max_verification_loops": 5},
            },
        }
        assert after_verification(state) == "translation"

    def test_paused_status_stops_loop(self) -> None:
        state = {"status": "paused", "behaviour_verified": False, "verification_loop_count": 0}
        assert after_verification(state) == "paused"


# ---------------------------------------------------------------------------
# after_review
# ---------------------------------------------------------------------------


class TestAfterReview:
    def test_passed_returns_rebase(self) -> None:
        state = {"review_passed": True, "review_loop_count": 0}
        assert after_review(state) == "rebase"

    def test_not_passed_below_max_returns_implementation(self) -> None:
        state = {"review_passed": False, "review_loop_count": 1}
        assert after_review(state) == "rework"

    def test_not_passed_at_max_returns_paused(self) -> None:
        state = {"review_passed": False, "review_loop_count": 3}
        assert after_review(state) == "paused"

    def test_missing_review_passed_treated_as_falsy(self) -> None:
        state = {"review_loop_count": 1}
        assert after_review(state) == "rework"

    def test_missing_review_loop_count_defaults_to_zero(self) -> None:
        state = {"review_passed": False}
        assert after_review(state) == "rework"

    def test_custom_max_review_dev_loops(self) -> None:
        state = {
            "review_passed": False,
            "review_loop_count": 5,
            "config_snapshot": {
                "pipeline": {"max_review_dev_loops": 5},
            },
        }
        assert after_review(state) == "paused"

    def test_custom_max_not_reached(self) -> None:
        state = {
            "review_passed": False,
            "review_loop_count": 3,
            "config_snapshot": {
                "pipeline": {"max_review_dev_loops": 5},
            },
        }
        assert after_review(state) == "rework"

    def test_paused_status_stops_loop(self) -> None:
        state = {"status": "paused", "review_passed": False, "review_loop_count": 0}
        assert after_review(state) == "paused"


# ---------------------------------------------------------------------------
# after_implementation
# ---------------------------------------------------------------------------


class TestAfterImplementation:
    def test_routes_to_e2e_when_commands_present(self) -> None:
        state = {"repo": {"e2e_test_commands": ["npx playwright test"]}}
        assert after_implementation(state) == "e2e_testing"

    def test_routes_to_review_when_no_commands(self) -> None:
        state = {"repo": {"e2e_test_commands": []}}
        assert after_implementation(state) == "review"

    def test_routes_to_review_when_no_repo(self) -> None:
        state = {}
        assert after_implementation(state) == "review"

    def test_routes_to_review_when_key_missing(self) -> None:
        state = {"repo": {}}
        assert after_implementation(state) == "review"

    def test_paused_takes_precedence(self) -> None:
        state = {"status": "paused", "repo": {"e2e_test_commands": ["npx playwright test"]}}
        assert after_implementation(state) == "paused"


# ---------------------------------------------------------------------------
# after_rework
# ---------------------------------------------------------------------------


class TestAfterRework:
    def test_routes_to_e2e_when_commands_present(self) -> None:
        state = {"repo": {"e2e_test_commands": ["npx playwright test"]}}
        assert after_rework(state) == "e2e_testing"

    def test_routes_to_review_when_no_commands(self) -> None:
        state = {"repo": {"e2e_test_commands": []}}
        assert after_rework(state) == "review"

    def test_routes_to_review_when_no_repo(self) -> None:
        state = {}
        assert after_rework(state) == "review"

    def test_paused_takes_precedence(self) -> None:
        state = {"status": "paused", "repo": {"e2e_test_commands": ["npx cypress run"]}}
        assert after_rework(state) == "paused"


# ---------------------------------------------------------------------------
# after_rebase
# ---------------------------------------------------------------------------


class TestAfterRebase:
    def test_clean_returns_delivery(self) -> None:
        state = {"rebase_clean": True}
        assert after_rebase(state) == "delivery"

    def test_not_clean_returns_paused(self) -> None:
        state = {"rebase_clean": False}
        assert after_rebase(state) == "paused"

    def test_missing_rebase_clean_defaults_to_delivery(self) -> None:
        """rebase_clean defaults to True — a fresh state routes to delivery."""
        state = {}
        assert after_rebase(state) == "delivery"


# ---------------------------------------------------------------------------
# _budget_exceeded
# ---------------------------------------------------------------------------


class TestBudgetExceeded:
    def test_under_budget(self) -> None:
        state = {"cost_usd": 5.0, "config_snapshot": {"pipeline": {"max_cost_usd": 10.0}}}
        assert _budget_exceeded(state) is False

    def test_at_budget(self) -> None:
        state = {"cost_usd": 10.0, "config_snapshot": {"pipeline": {"max_cost_usd": 10.0}}}
        assert _budget_exceeded(state) is True

    def test_over_budget(self) -> None:
        state = {"cost_usd": 15.0, "config_snapshot": {"pipeline": {"max_cost_usd": 10.0}}}
        assert _budget_exceeded(state) is True

    def test_defaults_to_10_usd(self) -> None:
        state = {"cost_usd": 10.0}
        assert _budget_exceeded(state) is True

    def test_zero_cost_not_exceeded(self) -> None:
        state = {}
        assert _budget_exceeded(state) is False


# ---------------------------------------------------------------------------
# Budget enforcement in edges
# ---------------------------------------------------------------------------


class TestBudgetEnforcementInEdges:
    """Budget exceeded → paused, regardless of other state."""

    def _over_budget_state(self, **extra: object) -> dict:
        return {
            "cost_usd": 20.0,
            "config_snapshot": {"pipeline": {"max_cost_usd": 10.0}},
            **extra,
        }

    def test_after_verification_pauses_on_budget(self) -> None:
        state = self._over_budget_state(behaviour_verified=True)
        assert after_verification(state) == "paused"

    def test_after_review_pauses_on_budget(self) -> None:
        state = self._over_budget_state(review_passed=True)
        assert after_review(state) == "paused"

    def test_after_implementation_pauses_on_budget(self) -> None:
        state = self._over_budget_state(repo={"e2e_test_commands": ["npx playwright"]})
        assert after_implementation(state) == "paused"

    def test_after_rework_pauses_on_budget(self) -> None:
        state = self._over_budget_state(repo={"e2e_test_commands": ["npx playwright"]})
        assert after_rework(state) == "paused"


# ---------------------------------------------------------------------------
# Pause reason inference
# ---------------------------------------------------------------------------


class TestInferPauseReason:
    def test_error_reason(self) -> None:
        state = {"error": "API failure"}
        assert _infer_pause_reason(state) == "error"

    def test_budget_exceeded_reason(self) -> None:
        state = {"cost_usd": 15.0, "config_snapshot": {"pipeline": {"max_cost_usd": 10.0}}}
        assert _infer_pause_reason(state) == "budget_exceeded"

    def test_rebase_conflict_reason(self) -> None:
        state = {"rebase_clean": False}
        assert _infer_pause_reason(state) == "rebase_conflict"

    def test_verification_circuit_breaker(self) -> None:
        state = {"verification_loop_count": 3, "config_snapshot": {"pipeline": {"max_verification_loops": 3}}}
        assert _infer_pause_reason(state) == "circuit_breaker"

    def test_review_circuit_breaker(self) -> None:
        state = {"review_loop_count": 3, "config_snapshot": {"pipeline": {"max_review_dev_loops": 3}}}
        assert _infer_pause_reason(state) == "circuit_breaker"

    def test_unknown_reason(self) -> None:
        state = {}
        assert _infer_pause_reason(state) == "unknown"

    def test_error_takes_priority_over_budget(self) -> None:
        state = {"error": "crash", "cost_usd": 15.0, "config_snapshot": {"pipeline": {"max_cost_usd": 10.0}}}
        assert _infer_pause_reason(state) == "error"


# ---------------------------------------------------------------------------
# Rework stall detection
# ---------------------------------------------------------------------------


class TestReworkIsStalled:
    def test_not_stalled_on_first_review(self) -> None:
        state = {"review_loop_count": 1, "review_finding_counts": [5]}
        assert _rework_is_stalled(state) is False

    def test_not_stalled_when_findings_decrease(self) -> None:
        state = {"review_loop_count": 2, "review_finding_counts": [5, 3]}
        assert _rework_is_stalled(state) is False

    def test_stalled_when_findings_same(self) -> None:
        state = {"review_loop_count": 2, "review_finding_counts": [5, 5]}
        assert _rework_is_stalled(state) is True

    def test_stalled_when_findings_increase(self) -> None:
        state = {"review_loop_count": 2, "review_finding_counts": [3, 5]}
        assert _rework_is_stalled(state) is True

    def test_not_stalled_without_history(self) -> None:
        state = {"review_loop_count": 2, "review_finding_counts": []}
        assert _rework_is_stalled(state) is False

    def test_not_stalled_without_field(self) -> None:
        state = {"review_loop_count": 2}
        assert _rework_is_stalled(state) is False


class TestAfterReviewStrategicPivot:
    """Review routes to implementation (not rework) when rework is stalled."""

    def test_stalled_rework_pivots_to_implementation(self) -> None:
        state = {
            "review_passed": False,
            "review_loop_count": 2,
            "review_finding_counts": [5, 5],
        }
        assert after_review(state) == "implementation"

    def test_improving_rework_continues_to_rework(self) -> None:
        state = {
            "review_passed": False,
            "review_loop_count": 2,
            "review_finding_counts": [5, 3],
        }
        assert after_review(state) == "rework"

    def test_budget_takes_precedence_over_pivot(self) -> None:
        state = {
            "review_passed": False,
            "review_loop_count": 2,
            "review_finding_counts": [5, 5],
            "cost_usd": 20.0,
            "config_snapshot": {"pipeline": {"max_cost_usd": 10.0}},
        }
        assert after_review(state) == "paused"

    def test_circuit_breaker_takes_precedence_over_pivot(self) -> None:
        state = {
            "review_passed": False,
            "review_loop_count": 3,
            "review_finding_counts": [5, 5, 5],
        }
        assert after_review(state) == "paused"
