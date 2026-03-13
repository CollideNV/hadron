"""Shared command allowlists for agent execution and test runners.

Both the agent backend (claude.py) and the test runner (testing.py)
validate commands against allowlists. Test runner patterns are the
shared base; the agent allowlist extends them with linters, formatters,
and read-only inspection commands.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Test runner patterns — shared between agent and test runner
# ---------------------------------------------------------------------------

TEST_RUNNER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^pytest(\s|$)"),
    re.compile(r"^((/[\w./-]+/)?python[\d.]*|python[\d.]*)\s+-m\s+pytest(\s|$)"),
    re.compile(r"^npm\s+(test|run\s+test)(\s|$)"),
    re.compile(r"^npx\s+(jest|vitest|mocha)(\s|$)"),
    re.compile(r"^cargo\s+test(\s|$)"),
    re.compile(r"^go\s+test(\s|$)"),
    re.compile(r"^mvn\s+(test|verify)(\s|$)"),
    re.compile(r"^gradle\s+test(\s|$)"),
    re.compile(r"^bundle\s+exec\s+rspec(\s|$)"),
    re.compile(r"^mix\s+test(\s|$)"),
    re.compile(r"^phpunit(\s|$)"),
    re.compile(r"^dotnet\s+test(\s|$)"),
    re.compile(r"^make\s+(test|check)(\s|$)"),
]

# ---------------------------------------------------------------------------
# Agent-only patterns — linters, formatters, read-only inspection
# ---------------------------------------------------------------------------

AGENT_EXTRA_PATTERNS: list[re.Pattern[str]] = [
    # Linters and formatters
    re.compile(r"^make\s+lint(\s|$)"),
    re.compile(r"^(ruff|flake8|mypy|pylint|black|isort)(\s|$)"),
    re.compile(r"^npx\s+(eslint|prettier|tsc)(\s|$)"),
    re.compile(r"^cargo\s+(clippy|fmt)(\s|$)"),
    re.compile(r"^go\s+(vet|fmt)(\s|$)"),
    # Build tools (read-only inspection)
    re.compile(r"^(pip|pip3)\s+list(\s|$)"),
    re.compile(r"^cat\s+"),
    re.compile(r"^head\s+"),
    re.compile(r"^tail\s+"),
    re.compile(r"^wc\s+"),
    re.compile(r"^find\s+\.\s+"),
    re.compile(r"^grep\s+"),
    re.compile(r"^ls(\s|$)"),
    re.compile(r"^tree(\s|$)"),
    re.compile(r"^echo(\s|$)"),
    re.compile(r"^pwd$"),
    re.compile(r"^which\s+"),
    re.compile(r"^diff\s+"),
    re.compile(r"^sleep\s+"),
]

# Combined allowlist for agent command validation
AGENT_COMMAND_ALLOWLIST: list[re.Pattern[str]] = TEST_RUNNER_PATTERNS + AGENT_EXTRA_PATTERNS

# Shell metacharacters that indicate chaining/piping — always rejected.
DANGEROUS_SHELL_CHARS = frozenset(";|`$\n")
DANGEROUS_SHELL_PATTERNS = ("&&", "||", "$(", ">", "<")

# Subcommand flags for `find` that enable arbitrary execution — always blocked.
FIND_DANGEROUS_FLAGS = ("-exec", "-execdir", "-delete", "-ok", "-okdir")
