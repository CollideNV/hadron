"""Tests for worker checkpoint resume logic."""

from __future__ import annotations

import pytest

from hadron.worker.main import (
    OVERRIDE_NODE_MAP,
    PIPELINE_NODE_ORDER,
    _pick_resume_node,
)


# ---------------------------------------------------------------------------
# _pick_resume_node — single overrides
# ---------------------------------------------------------------------------


class TestPickResumeNodeSingle:
    def test_rebase_clean(self) -> None:
        assert _pick_resume_node({"rebase_clean": True}) == "rebase"

    def test_review_passed(self) -> None:
        assert _pick_resume_node({"review_passed": True}) == "review"

    def test_behaviour_verified(self) -> None:
        assert _pick_resume_node({"behaviour_verified": True}) == "verification"


# ---------------------------------------------------------------------------
# _pick_resume_node — multiple overrides (latest in pipeline order wins)
# ---------------------------------------------------------------------------


class TestPickResumeNodeMultiple:
    def test_review_and_verification(self) -> None:
        # review (index 6) > verification (index 4)
        assert _pick_resume_node({"review_passed": True, "behaviour_verified": True}) == "review"

    def test_rebase_and_review(self) -> None:
        # rebase (index 7) > review (index 6)
        assert _pick_resume_node({"rebase_clean": True, "review_passed": True}) == "rebase"

    def test_all_three(self) -> None:
        # rebase is latest
        result = _pick_resume_node({
            "rebase_clean": True,
            "review_passed": True,
            "behaviour_verified": True,
        })
        assert result == "rebase"


# ---------------------------------------------------------------------------
# _pick_resume_node — edge cases
# ---------------------------------------------------------------------------


class TestPickResumeNodeEdgeCases:
    def test_empty_dict(self) -> None:
        assert _pick_resume_node({}) == "paused"

    def test_unrecognized_keys_only(self) -> None:
        assert _pick_resume_node({"unknown_key": True, "another": 42}) == "paused"

    def test_mix_recognized_and_unrecognized(self) -> None:
        result = _pick_resume_node({"garbage": True, "review_passed": True})
        assert result == "review"

    def test_false_values_still_map(self) -> None:
        """The function checks key presence, not truthiness."""
        assert _pick_resume_node({"rebase_clean": False}) == "rebase"

    def test_none_value_still_maps(self) -> None:
        assert _pick_resume_node({"review_passed": None}) == "review"


# ---------------------------------------------------------------------------
# Constant consistency
# ---------------------------------------------------------------------------


class TestConstants:
    def test_all_mapped_nodes_in_pipeline_order(self) -> None:
        for node in OVERRIDE_NODE_MAP.values():
            assert node in PIPELINE_NODE_ORDER, f"{node} not in PIPELINE_NODE_ORDER"

    def test_override_node_map_has_expected_keys(self) -> None:
        expected = {"rebase_clean", "review_passed", "behaviour_verified"}
        assert set(OVERRIDE_NODE_MAP.keys()) == expected
