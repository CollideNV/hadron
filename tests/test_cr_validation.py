"""Tests for CR validation and test_command validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from hadron.models.cr import RawChangeRequest, validate_test_command

# Minimal valid fields for constructing a RawChangeRequest.
_BASE = {"title": "Test CR", "description": "A change request"}


class TestRawChangeRequest:
    """RawChangeRequest model validation."""

    def test_minimal_cr(self) -> None:
        cr = RawChangeRequest(**_BASE)
        assert cr.title == "Test CR"
        assert cr.repo_urls == []

    def test_single_repo_url(self) -> None:
        cr = RawChangeRequest(**_BASE, repo_urls=["https://github.com/org/repo"])
        assert cr.repo_urls == ["https://github.com/org/repo"]

    def test_multiple_repo_urls(self) -> None:
        cr = RawChangeRequest(
            **_BASE,
            repo_urls=["https://github.com/org/auth", "https://github.com/org/api"],
        )
        assert len(cr.repo_urls) == 2

    def test_no_language_or_test_command_field(self) -> None:
        """CR model should not have language or test_command — these are auto-detected."""
        cr = RawChangeRequest(**_BASE)
        assert not hasattr(cr, "language")
        assert not hasattr(cr, "test_command")


class TestAllowedCommands:
    """Allowed base commands should be accepted."""

    @pytest.mark.parametrize("cmd", [
        "pytest",
        "python -m pytest",
        "npm test",
        "npm run test",
        "npx jest",
        "yarn test",
        "pnpm test",
        "go test",
        "cargo test",
        "mvn test",
        "mvn verify",
        "gradle test",
        "gradlew test",
        "./gradlew test",
        "make test",
        "make check",
        "bundle exec rspec",
        "phpunit",
        "dotnet test",
    ])
    def test_allowed_base_command(self, cmd: str) -> None:
        assert validate_test_command(cmd) == cmd


class TestAllowedCommandsWithFlags:
    """Allowed commands with trailing flags/args should pass."""

    @pytest.mark.parametrize("cmd", [
        "pytest -x --timeout=30",
        "pytest tests/unit -v --tb=short",
        "npm test -- --coverage",
        "go test ./...",
        "cargo test --release",
        "make test VERBOSE=1",
        "python -m pytest -k test_foo",
    ])
    def test_allowed_with_flags(self, cmd: str) -> None:
        assert validate_test_command(cmd) == cmd


class TestShellInjectionBlocked:
    """Shell metacharacters must be rejected."""

    @pytest.mark.parametrize("cmd", [
        "pytest; rm -rf /",
        "pytest && curl evil.com",
        "pytest || true",
        "pytest | tee log.txt",
        "pytest `whoami`",
        "pytest $(whoami)",
        "pytest > /dev/null",
        "pytest < /dev/null",
        "pytest\nwhoami",
    ])
    def test_metachar_blocked(self, cmd: str) -> None:
        with pytest.raises(ValueError, match="disallowed shell metacharacters"):
            validate_test_command(cmd)


class TestUnknownCommandBlocked:
    """Unknown base commands must be rejected."""

    @pytest.mark.parametrize("cmd", [
        "bash -c 'echo pwned'",
        "sh -c 'echo pwned'",
        "curl http://evil.com",
        "rm -rf /",
        "python evil.py",
        "node malicious.js",
    ])
    def test_unknown_base_blocked(self, cmd: str) -> None:
        with pytest.raises(ValueError, match="test_command must start with one of"):
            validate_test_command(cmd)


class TestEmptyRejected:
    """Empty string should raise ValueError."""

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            validate_test_command("")

    def test_whitespace_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            validate_test_command("   ")


class TestWhitespaceStripped:
    """Leading/trailing whitespace should be stripped."""

    def test_leading_trailing_whitespace(self) -> None:
        assert validate_test_command("  pytest -x  ") == "pytest -x"
