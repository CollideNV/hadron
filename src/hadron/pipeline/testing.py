"""Shared test runner used by TDD, Rebase, and Delivery nodes."""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


async def run_test_command(
    worktree_path: str,
    test_command: str,
    cr_id: str,
    timeout: int = 120,
) -> tuple[bool, str]:
    """Run a test command inside a worktree and return (passed, output).

    - Interpolates ``{cr_id}`` in the command.
    - Uses *cwd* instead of a ``cd … &&`` shell hack.
    - Kills the process on timeout rather than leaking it.
    """
    cmd = test_command.replace("{cr_id}", cr_id)

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
