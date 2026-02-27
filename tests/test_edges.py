"""Tests for pipeline conditional edge functions."""

from __future__ import annotations

import pytest

from hadron.pipeline.edges import after_verification, after_review, after_rebase


# ---------------------------------------------------------------------------
# after_verification
# ---------------------------------------------------------------------------


class TestAfterVerification:
    def test_verified_returns_tdd(self) -> None:
        state = {"behaviour_verified": True, "verification_loop_count": 0}
        assert after_verification(state) == "tdd"

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


# ---------------------------------------------------------------------------
# after_review
# ---------------------------------------------------------------------------


class TestAfterReview:
    def test_passed_returns_rebase(self) -> None:
        state = {"review_passed": True, "review_loop_count": 0}
        assert after_review(state) == "rebase"

    def test_not_passed_below_max_returns_tdd(self) -> None:
        state = {"review_passed": False, "review_loop_count": 1}
        assert after_review(state) == "tdd"

    def test_not_passed_at_max_returns_paused(self) -> None:
        state = {"review_passed": False, "review_loop_count": 3}
        assert after_review(state) == "paused"

    def test_missing_review_passed_treated_as_falsy(self) -> None:
        state = {"review_loop_count": 1}
        assert after_review(state) == "tdd"

    def test_missing_review_loop_count_defaults_to_zero(self) -> None:
        state = {"review_passed": False}
        assert after_review(state) == "tdd"

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
        assert after_review(state) == "tdd"


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
