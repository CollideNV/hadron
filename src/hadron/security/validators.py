"""Unified command validation for agent execution and test runners.

Both the agent backend and the test runner share the same core validation
logic. This module provides the building blocks and composed validators.
"""

from __future__ import annotations

import re as _re

from hadron.security.allowlists import (
    AGENT_COMMAND_ALLOWLIST,
    DANGEROUS_SHELL_CHARS,
    DANGEROUS_SHELL_PATTERNS,
    FIND_DANGEROUS_FLAGS,
    TEST_RUNNER_PATTERNS,
)

# Patterns that agents add but our runtime already handles (we capture
# stdout+stderr and truncate).  Stripped before validation so the agent
# doesn't burn retries on harmless pipe/redirect suffixes.
_HARMLESS_PIPE = _re.compile(
    r"\s*\|\s*(?:head|tail)\s+-(?:n\s*)?\d+"  # | head -N / | tail -n N
    r"|\s*\|\s*tee\s+\S+",                     # | tee file
)
_STDERR_MERGE = _re.compile(r"\s*2>&1")

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


def _strip_cd_prefix(cmd: str) -> str | None:
    """If cmd starts with ``cd <dir> && <rest>``, return <rest>.

    Only strips a single ``cd`` prefix; nested chaining is rejected.
    Returns None if there's no ``cd`` prefix (caller uses original cmd).
    """
    import re
    m = re.match(r"^cd\s+\S+\s*&&\s*(.+)$", cmd)
    return m.group(1).strip() if m else None


def sanitize_agent_command(cmd: str) -> str:
    """Strip harmless pipe/redirect suffixes that agents add unnecessarily.

    Our runtime already captures stdout+stderr and truncates, so patterns
    like ``2>&1 | head -200`` are redundant.  Stripping them avoids wasting
    retries on a command the validator would otherwise reject.

    Returns the cleaned command (may be unchanged if nothing was stripped).
    """
    # Strip from the inner command if there's a cd prefix
    cd_inner = _strip_cd_prefix(cmd)
    if cd_inner is not None:
        cleaned_inner = _strip_harmless_suffixes(cd_inner)
        if cleaned_inner != cd_inner:
            prefix = cmd[: cmd.index("&&") + 2].strip()
            return f"{prefix} {cleaned_inner}"
        return cmd

    return _strip_harmless_suffixes(cmd)


def _strip_harmless_suffixes(cmd: str) -> str:
    """Remove trailing 2>&1, | head/tail, etc. from a command string."""
    original = cmd
    # Iteratively strip from the end (order matters: pipe first, then stderr)
    changed = True
    while changed:
        changed = False
        # Strip trailing 2>&1
        m = _STDERR_MERGE.search(cmd)
        if m and m.end() == len(cmd):
            cmd = cmd[:m.start()].rstrip()
            changed = True
        # Strip trailing | head/tail/tee
        m = _HARMLESS_PIPE.search(cmd)
        if m and m.end() == len(cmd):
            cmd = cmd[:m.start()].rstrip()
            changed = True
    return cmd or original


def validate_agent_command(cmd: str) -> bool:
    """Check whether a command from an agent is allowed.

    Blocks shell metacharacters, chaining patterns, and unknown prefixes.
    Additional restrictions apply to ``find`` (dangerous flags).

    Allows a single ``cd <dir> && <allowed_cmd>`` prefix as a safe pattern
    for running commands in subdirectories (e.g. monorepo test commands).
    """
    # Allow a single cd prefix — validate the inner command
    inner = _strip_cd_prefix(cmd)
    if inner is not None:
        return validate_agent_command(inner)

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
