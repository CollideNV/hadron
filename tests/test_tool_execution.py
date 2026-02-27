"""Tests for _execute_tool and _safe_resolve in the Claude agent backend."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from hadron.agent.claude import _execute_tool, _safe_resolve


# ---------------------------------------------------------------------------
# _safe_resolve
# ---------------------------------------------------------------------------


class TestSafeResolve:
    def test_simple_relative_path(self, tmp_workdir: Path) -> None:
        resolved = _safe_resolve(str(tmp_workdir), "hello.txt")
        assert resolved == tmp_workdir / "hello.txt"

    def test_nested_relative_path(self, tmp_workdir: Path) -> None:
        resolved = _safe_resolve(str(tmp_workdir), "subdir/nested.txt")
        assert resolved == tmp_workdir / "subdir" / "nested.txt"

    def test_dot_path(self, tmp_workdir: Path) -> None:
        resolved = _safe_resolve(str(tmp_workdir), ".")
        assert resolved == tmp_workdir.resolve()

    def test_traversal_blocked(self, tmp_workdir: Path) -> None:
        with pytest.raises(ValueError, match="Path escapes working directory"):
            _safe_resolve(str(tmp_workdir), "../../../etc/passwd")

    def test_absolute_path_outside_blocked(self, tmp_workdir: Path) -> None:
        with pytest.raises(ValueError, match="Path escapes working directory"):
            _safe_resolve(str(tmp_workdir), "/etc/passwd")

    def test_traversal_via_subdir_blocked(self, tmp_workdir: Path) -> None:
        with pytest.raises(ValueError, match="Path escapes working directory"):
            _safe_resolve(str(tmp_workdir), "subdir/../../etc/passwd")

    def test_symlink_escape_blocked(self, tmp_workdir: Path) -> None:
        link = tmp_workdir / "escape_link"
        link.symlink_to("/tmp")
        with pytest.raises(ValueError, match="Path escapes working directory"):
            _safe_resolve(str(tmp_workdir), "escape_link/some_file")

    def test_path_within_dir_via_dotdot_ok(self, tmp_workdir: Path) -> None:
        """subdir/../hello.txt resolves back inside the workdir — should be allowed."""
        resolved = _safe_resolve(str(tmp_workdir), "subdir/../hello.txt")
        assert resolved == tmp_workdir / "hello.txt"


# ---------------------------------------------------------------------------
# _execute_tool — read_file
# ---------------------------------------------------------------------------


class TestReadFile:
    @pytest.mark.asyncio
    async def test_read_existing_file(self, tmp_workdir: Path) -> None:
        result = await _execute_tool("read_file", {"path": "hello.txt"}, str(tmp_workdir))
        assert result == "hello world"

    @pytest.mark.asyncio
    async def test_read_missing_file(self, tmp_workdir: Path) -> None:
        result = await _execute_tool("read_file", {"path": "nope.txt"}, str(tmp_workdir))
        assert "File not found" in result

    @pytest.mark.asyncio
    async def test_read_traversal_blocked(self, tmp_workdir: Path) -> None:
        result = await _execute_tool(
            "read_file", {"path": "../../../etc/passwd"}, str(tmp_workdir)
        )
        assert "Path escapes working directory" in result

    @pytest.mark.asyncio
    async def test_read_large_file_truncated(self, tmp_workdir: Path) -> None:
        big = tmp_workdir / "big.txt"
        big.write_text("x" * 200_000)
        result = await _execute_tool("read_file", {"path": "big.txt"}, str(tmp_workdir))
        assert len(result) < 200_000
        assert "truncated" in result


# ---------------------------------------------------------------------------
# _execute_tool — write_file
# ---------------------------------------------------------------------------


class TestWriteFile:
    @pytest.mark.asyncio
    async def test_write_new_file(self, tmp_workdir: Path) -> None:
        result = await _execute_tool(
            "write_file", {"path": "new.txt", "content": "hi"}, str(tmp_workdir)
        )
        assert "File written" in result
        assert (tmp_workdir / "new.txt").read_text() == "hi"

    @pytest.mark.asyncio
    async def test_write_creates_parent_dirs(self, tmp_workdir: Path) -> None:
        result = await _execute_tool(
            "write_file",
            {"path": "a/b/c.txt", "content": "deep"},
            str(tmp_workdir),
        )
        assert "File written" in result
        assert (tmp_workdir / "a" / "b" / "c.txt").read_text() == "deep"

    @pytest.mark.asyncio
    async def test_write_traversal_blocked(self, tmp_workdir: Path) -> None:
        result = await _execute_tool(
            "write_file",
            {"path": "../../evil.txt", "content": "pwned"},
            str(tmp_workdir),
        )
        assert "Path escapes working directory" in result


# ---------------------------------------------------------------------------
# _execute_tool — list_directory
# ---------------------------------------------------------------------------


class TestListDirectory:
    @pytest.mark.asyncio
    async def test_list_root(self, tmp_workdir: Path) -> None:
        result = await _execute_tool("list_directory", {}, str(tmp_workdir))
        assert "hello.txt" in result
        assert "subdir" in result

    @pytest.mark.asyncio
    async def test_list_subdir(self, tmp_workdir: Path) -> None:
        result = await _execute_tool(
            "list_directory", {"path": "subdir"}, str(tmp_workdir)
        )
        assert "nested.txt" in result

    @pytest.mark.asyncio
    async def test_list_traversal_blocked(self, tmp_workdir: Path) -> None:
        result = await _execute_tool(
            "list_directory", {"path": "../../"}, str(tmp_workdir)
        )
        assert "Path escapes working directory" in result

    @pytest.mark.asyncio
    async def test_list_not_a_directory(self, tmp_workdir: Path) -> None:
        result = await _execute_tool(
            "list_directory", {"path": "hello.txt"}, str(tmp_workdir)
        )
        assert "Not a directory" in result


# ---------------------------------------------------------------------------
# _execute_tool — run_command
# ---------------------------------------------------------------------------


class TestRunCommand:
    @pytest.mark.asyncio
    async def test_run_simple_command(self, tmp_workdir: Path) -> None:
        result = await _execute_tool(
            "run_command", {"command": "echo hello"}, str(tmp_workdir)
        )
        assert "Exit code: 0" in result
        assert "hello" in result

    @pytest.mark.asyncio
    async def test_run_command_timeout_kills_process(self, tmp_workdir: Path) -> None:
        """A long-running command should be killed on timeout, not leak a zombie."""
        from unittest.mock import patch

        # Use a very short timeout to trigger it in tests
        with patch("hadron.agent.claude.asyncio.wait_for", side_effect=asyncio.TimeoutError):
            # We need to also mock create_subprocess_shell to give us a controllable process
            from unittest.mock import AsyncMock, MagicMock

            mock_proc = MagicMock()
            mock_proc.kill = MagicMock()
            mock_proc.wait = AsyncMock()

            with patch("hadron.agent.claude.asyncio.create_subprocess_shell", return_value=mock_proc):
                result = await _execute_tool(
                    "run_command", {"command": "sleep 999"}, str(tmp_workdir)
                )

            assert "timed out" in result.lower()
            mock_proc.kill.assert_called_once()
            mock_proc.wait.assert_awaited_once()


# ---------------------------------------------------------------------------
# _execute_tool — unknown tool
# ---------------------------------------------------------------------------


class TestUnknownTool:
    @pytest.mark.asyncio
    async def test_unknown_tool(self, tmp_workdir: Path) -> None:
        result = await _execute_tool("delete_everything", {}, str(tmp_workdir))
        assert "Unknown tool" in result
