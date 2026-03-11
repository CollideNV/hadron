"""Unified command validation for agent execution and test runners.

Both the agent backend and the test runner share the same core validation
logic. This module provides the building blocks and composed validators.
"""

from __future__ import annotations

from hadron.security.allowlists import (
    AGENT_COMMAND_ALLOWLIST,
    DANGEROUS_SHELL_CHARS,
    DANGEROUS_SHELL_PATTERNS,
    FIND_DANGEROUS_FLAGS,
    TEST_RUNNER_PATTERNS,
)

# Extra characters rejected for test commands (superset of DANGEROUS_SHELL_CHARS).
_TEST_EXTRA_DANGEROUS = frozenset("&()<>")


def _has_dangerous_shell_chars(cmd: str) -> bool:
    """Return True if *cmd* contains any blocked shell metacharacter."""
    return any(c in cmd for c in DANGEROUS_SHELL_CHARS)


def _has_dangerous_shell_patterns(cmd: str) -> bool:
    """Return True if *cmd* contains blocked shell chaining patterns."""
    return any(pat in cmd for pat in DANGEROUS_SHELL_PATTERNS)


def _has_dangerous_find_flags(cmd: str) -> bool:
    """Return True if a ``find`` command uses exec/delete flags."""
    return cmd.startswith("find ") and any(flag in cmd for flag in FIND_DANGEROUS_FLAGS)


def validate_agent_command(cmd: str) -> bool:
    """Check whether a command from an agent is allowed.

    Blocks shell metacharacters, chaining patterns, and unknown prefixes.
    Additional restrictions apply to ``find`` (dangerous flags).
    """
    if _has_dangerous_shell_chars(cmd):
        return False
    if _has_dangerous_shell_patterns(cmd):
        return False
    if not any(p.match(cmd) for p in AGENT_COMMAND_ALLOWLIST):
        return False
    if _has_dangerous_find_flags(cmd):
        return False
    return True


def validate_test_command(cmd: str) -> bool:
    """Check whether a test command matches the allowlist.

    Stricter than agent validation: also rejects ``&``, parentheses, and
    angle brackets, and only accepts known test runner patterns.
    """
    if _has_dangerous_shell_chars(cmd):
        return False
    if any(c in cmd for c in _TEST_EXTRA_DANGEROUS):
        return False
    return any(p.match(cmd) for p in TEST_RUNNER_PATTERNS)
