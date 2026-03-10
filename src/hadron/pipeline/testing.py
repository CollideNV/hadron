"""Shared test runner used by TDD, Rebase, and Delivery nodes."""

from __future__ import annotations

import asyncio
import logging
import re

logger = logging.getLogger(__name__)

# Allowlist of safe test command patterns.
# Each pattern is matched against the full command string.
_ALLOWED_COMMANDS: list[re.Pattern[str]] = [
    re.compile(r"^pytest(\s|$)"),
    re.compile(r"^python\s+-m\s+pytest(\s|$)"),
    re.compile(r"^npm\s+test(\s|$)"),
    re.compile(r"^npx\s+(jest|vitest|mocha)(\s|$)"),
    re.compile(r"^cargo\s+test(\s|$)"),
    re.compile(r"^go\s+test(\s|$)"),
    re.compile(r"^mvn\s+test(\s|$)"),
    re.compile(r"^gradle\s+test(\s|$)"),
    re.compile(r"^bundle\s+exec\s+rspec(\s|$)"),
    re.compile(r"^mix\s+test(\s|$)"),
    re.compile(r"^phpunit(\s|$)"),
    re.compile(r"^dotnet\s+test(\s|$)"),
    re.compile(r"^make\s+test(\s|$)"),
]


def validate_test_command(cmd: str) -> bool:
    """Check whether a test command matches the allowlist.

    Rejects anything that could be shell injection (pipes, semicolons,
    subshells, redirects) unless it matches a known-safe pattern.
    """
    # Reject obvious shell metacharacters regardless of allowlist
    if any(c in cmd for c in (";", "|", "&", "`", "$", "(", ")", "<", ">", "\n")):
        return False
    return any(p.match(cmd) for p in _ALLOWED_COMMANDS)


async def run_test_command(
    worktree_path: str,
    test_command: str,
    cr_id: str,
    timeout: int = 120,
) -> tuple[bool, str]:
    """Run a test command inside a worktree and return (passed, output).

    - Validates the command against an allowlist before execution.
    - Interpolates ``{cr_id}`` in the command.
    - Uses *cwd* instead of a ``cd … &&`` shell hack.
    - Kills the process on timeout rather than leaking it.
    """
    # Defense-in-depth: reject cr_id values that aren't safe for shell interpolation.
    # Server-generated cr_ids are always "CR-<hex>", but validate in case of misuse.
    if not re.fullmatch(r"[A-Za-z0-9_-]+", cr_id):
        logger.error("cr_id rejected by safety check: %r", cr_id)
        return False, f"Error: cr_id contains unsafe characters: {cr_id!r}"

    cmd = test_command.replace("{cr_id}", cr_id)

    if not validate_test_command(cmd):
        logger.error("Test command rejected by allowlist: %r", cmd)
        return False, f"Error: test command rejected by allowlist: {cmd!r}"

    proc = await asyncio.create_subprocess_shell(
        cmd,
        cwd=worktree_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return False, f"Error: test command timed out after {timeout}s (process killed)"

    output = stdout.decode(errors="replace")
    return proc.returncode == 0, output
