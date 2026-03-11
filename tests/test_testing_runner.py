"""Tests for the shared test runner (pipeline/testing.py)."""

from __future__ import annotations

import pytest

from hadron.pipeline.testing import run_test_command


class TestRunTestCommand:
    @pytest.mark.asyncio
    async def test_successful_pytest(self, tmp_path) -> None:
        # Create a trivial test file so pytest succeeds
        (tmp_path / "test_ok.py").write_text("def test_pass(): pass\n")
        passed, output = await run_test_command(
            str(tmp_path), "pytest -x", "CR-abc123"
        )
        assert passed is True

    @pytest.mark.asyncio
    async def test_failing_pytest(self, tmp_path) -> None:
        (tmp_path / "test_fail.py").write_text("def test_fail(): assert False\n")
        passed, output = await run_test_command(
            str(tmp_path), "pytest -x", "CR-abc"
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
            str(tmp_path), "pytest -x", "CR-abc",
            timeout=1,
        )
        assert passed is False
        assert "timed out" in output
