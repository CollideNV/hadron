"""Tests for the stage diff capture helper."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from hadron.models.events import EventType
from hadron.pipeline.nodes.diff_capture import (
    _compute_diff_stats,
    _parse_feature_content,
    emit_stage_diff,
)


class TestComputeDiffStats:
    def test_counts_files_insertions_deletions(self) -> None:
        diff = (
            "diff --git a/foo.py b/foo.py\n"
            "--- a/foo.py\n"
            "+++ b/foo.py\n"
            "@@ -1,3 +1,4 @@\n"
            " context\n"
            "+added\n"
            "-removed\n"
            "diff --git a/bar.py b/bar.py\n"
            "+another add\n"
        )
        stats = _compute_diff_stats(diff)
        assert stats["files_changed"] == 2
        assert stats["insertions"] == 2
        assert stats["deletions"] == 1

    def test_empty_diff(self) -> None:
        stats = _compute_diff_stats("")
        assert stats == {"files_changed": 0, "insertions": 0, "deletions": 0}

    def test_ignores_plus_minus_in_headers(self) -> None:
        diff = (
            "diff --git a/f.py b/f.py\n"
            "--- a/f.py\n"
            "+++ b/f.py\n"
            "+real addition\n"
        )
        stats = _compute_diff_stats(diff)
        assert stats["insertions"] == 1
        assert stats["deletions"] == 0


class TestParseFeatureContent:
    def test_parses_markdown_format(self) -> None:
        raw = (
            "### features/login.feature\n\n"
            "```\n"
            "Feature: Login\n"
            "  Scenario: Valid credentials\n"
            "```\n\n"
            "### features/signup.feature\n\n"
            "```\n"
            "Feature: Signup\n"
            "```"
        )
        files = _parse_feature_content(raw)
        assert len(files) == 2
        assert files[0]["path"] == "features/login.feature"
        assert "Feature: Login" in files[0]["content"]
        assert files[1]["path"] == "features/signup.feature"
        assert "Feature: Signup" in files[1]["content"]

    def test_empty_input(self) -> None:
        assert _parse_feature_content("") == []
        assert _parse_feature_content("   ") == []

    def test_single_file(self) -> None:
        raw = "### path/to/file.feature\n\n```\ncontent here\n```"
        files = _parse_feature_content(raw)
        assert len(files) == 1
        assert files[0]["path"] == "path/to/file.feature"
        assert files[0]["content"] == "content here"


class TestEmitStageDiff:
    @pytest.mark.asyncio
    async def test_emits_stage_diff_event(self) -> None:
        event_bus = AsyncMock()
        wm = AsyncMock()
        wm.get_diff = AsyncMock(return_value="diff --git a/f.py b/f.py\n+hello")

        await emit_stage_diff(
            event_bus, "cr-1", "implementation", "backend",
            wm, "/tmp/wt", "main",
        )

        event_bus.emit.assert_called_once()
        event = event_bus.emit.call_args[0][0]
        assert event.event_type == EventType.STAGE_DIFF
        assert event.stage == "implementation"
        assert event.cr_id == "cr-1"
        assert event.data["repo"] == "backend"
        assert event.data["diff_truncated"] is False
        assert event.data["stats"]["files_changed"] == 1
        assert event.data["stats"]["insertions"] == 1
        assert "files" not in event.data  # No feature content

    @pytest.mark.asyncio
    async def test_includes_feature_files(self) -> None:
        event_bus = AsyncMock()
        wm = AsyncMock()
        wm.get_diff = AsyncMock(return_value="")

        feature_md = "### features/login.feature\n\n```\nFeature: Login\n```"
        await emit_stage_diff(
            event_bus, "cr-1", "behaviour_translation", "backend",
            wm, "/tmp/wt", "main",
            feature_content=feature_md,
        )

        event = event_bus.emit.call_args[0][0]
        assert "files" in event.data
        assert len(event.data["files"]) == 1
        assert event.data["files"][0]["path"] == "features/login.feature"
        assert event.data["files_truncated"] is False

    @pytest.mark.asyncio
    async def test_truncates_large_diff(self) -> None:
        event_bus = AsyncMock()
        wm = AsyncMock()
        large_diff = "diff --git a/f.py b/f.py\n" + "+x\n" * 100_000
        wm.get_diff = AsyncMock(return_value=large_diff)

        await emit_stage_diff(
            event_bus, "cr-1", "implementation", "backend",
            wm, "/tmp/wt", "main",
        )

        event = event_bus.emit.call_args[0][0]
        assert event.data["diff_truncated"] is True
        assert len(event.data["diff"]) == 50_000

    @pytest.mark.asyncio
    async def test_handles_get_diff_failure(self) -> None:
        event_bus = AsyncMock()
        wm = AsyncMock()
        wm.get_diff = AsyncMock(side_effect=RuntimeError("git failed"))

        await emit_stage_diff(
            event_bus, "cr-1", "implementation", "backend",
            wm, "/tmp/wt", "main",
        )

        event = event_bus.emit.call_args[0][0]
        assert event.data["diff"] == ""
        assert event.data["stats"]["files_changed"] == 0
