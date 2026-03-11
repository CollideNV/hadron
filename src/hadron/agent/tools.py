"""Agent tool definitions and execution engine.

Handles tool definition building, safe file I/O, command validation,
environment scrubbing, and tool dispatch.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from hadron.config.limits import MAX_COMMAND_OUTPUT_CHARS, MAX_READ_FILE_CHARS
from hadron.security.validators import validate_agent_command
from hadron.utils.text import truncate

logger = logging.getLogger(__name__)

# Env var prefixes / keys stripped from agent subprocess environments.
_SCRUB_PREFIXES = ("HADRON_", "ANTHROPIC_", "OPENAI_", "GOOGLE_", "GITHUB_", "AZURE_", "AWS_")
_SCRUB_KEYS = frozenset({
    "DATABASE_URL", "REDIS_URL", "SECRET_KEY", "API_KEY",
    "GH_TOKEN", "GITLAB_TOKEN", "BITBUCKET_TOKEN",
})


# ------------------------------------------------------------------
# Tool definitions
# ------------------------------------------------------------------

_ALL_TOOL_DEFS: dict[str, dict[str, Any]] = {
    "read_file": {
        "name": "read_file",
        "description": "Read the contents of a file. Path is relative to the working directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to read"},
            },
            "required": ["path"],
        },
    },
    "write_file": {
        "name": "write_file",
        "description": (
            "Write content to a file. Creates parent directories if needed. "
            "Path is relative to the working directory."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write"},
                "content": {"type": "string", "description": "File content"},
            },
            "required": ["path", "content"],
        },
    },
    "list_directory": {
        "name": "list_directory",
        "description": "List files and directories. Path is relative to the working directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path (default: '.')",
                    "default": ".",
                },
            },
        },
    },
    "run_command": {
        "name": "run_command",
        "description": "Run a shell command in the working directory. Use for running tests, linting, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
            },
            "required": ["command"],
        },
    },
}


def make_tools(allowed: list[str], working_dir: str | None) -> list[dict]:
    """Build Anthropic tool definitions for the allowed tool set."""
    return [_ALL_TOOL_DEFS[name] for name in allowed if name in _ALL_TOOL_DEFS]


# ------------------------------------------------------------------
# Path safety
# ------------------------------------------------------------------


def safe_resolve(working_dir: str, user_path: str) -> Path:
    """Resolve a user-provided path and ensure it stays within working_dir.

    Raises ValueError if the resolved path escapes the working directory,
    or if any component of the path is a symlink pointing outside the root.
    """
    root = Path(working_dir).resolve()
    resolved = (root / user_path).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(
            f"Path escapes working directory: {user_path}"
        )
    # Walk each ancestor to detect symlinks that point outside the root.
    # This prevents an agent from creating a symlink inside the worktree
    # that targets a file outside it (symlink traversal attack).
    current = root
    for part in resolved.relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            link_target = current.resolve()
            if not link_target.is_relative_to(root):
                raise ValueError(
                    f"Symlink escapes working directory: {user_path} -> {link_target}"
                )
    return resolved


# ------------------------------------------------------------------
# Environment scrubbing
# ------------------------------------------------------------------


def scrubbed_env() -> dict[str, str]:
    """Return a copy of os.environ with secrets stripped.

    Keeps PATH and other non-sensitive vars so tools like git/pytest still work.
    """
    return {
        k: v
        for k, v in os.environ.items()
        if k not in _SCRUB_KEYS and not k.startswith(_SCRUB_PREFIXES)
    }


# ------------------------------------------------------------------
# Tool execution
# ------------------------------------------------------------------


def _execute_read_file(working_dir: str, input_data: dict[str, Any]) -> str:
    """Read a file within the working directory."""
    path = safe_resolve(working_dir, input_data["path"])
    if not path.is_file():
        return f"Error: File not found: {input_data['path']}"
    content = path.read_text()
    return truncate(content, MAX_READ_FILE_CHARS)


def _execute_write_file(working_dir: str, input_data: dict[str, Any]) -> str:
    """Write content to a file, creating parent directories as needed."""
    path = safe_resolve(working_dir, input_data["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(input_data["content"])
    return f"File written: {input_data['path']}"


def _execute_list_directory(working_dir: str, input_data: dict[str, Any]) -> str:
    """List files and directories."""
    dir_path = safe_resolve(working_dir, input_data.get("path", "."))
    if not dir_path.is_dir():
        return f"Error: Not a directory: {input_data.get('path', '.')}"
    entries = sorted(dir_path.iterdir())
    lines = []
    for e in entries[:200]:
        prefix = "d " if e.is_dir() else "f "
        lines.append(f"{prefix}{e.name}")
    return "\n".join(lines) if lines else "(empty directory)"


async def _execute_run_command(working_dir: str, input_data: dict[str, Any]) -> str:
    """Run a shell command with safety validation and output truncation."""
    cmd = input_data["command"]
    if not validate_agent_command(cmd):
        return f"Error: Command rejected by safety filter: {cmd!r}"
    proc = await asyncio.create_subprocess_shell(
        cmd,
        cwd=working_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env={**scrubbed_env(), "PYTHONDONTWRITEBYTECODE": "1"},
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return "Error: Command timed out after 120s (process killed)"
    output = stdout.decode(errors="replace")
    output = truncate(output, MAX_COMMAND_OUTPUT_CHARS)
    return f"Exit code: {proc.returncode}\n{output}"


_TOOL_DISPATCH: dict[str, Any] = {
    "read_file": _execute_read_file,
    "write_file": _execute_write_file,
    "list_directory": _execute_list_directory,
    "run_command": _execute_run_command,
}


async def execute_tool(
    name: str, input_data: dict[str, Any], working_dir: str
) -> str:
    """Execute a tool call and return the result string."""
    handler = _TOOL_DISPATCH.get(name)
    if handler is None:
        return f"Error: Unknown tool: {name}"
    try:
        result = handler(working_dir, input_data)
        if asyncio.iscoroutine(result):
            return await result
        return result
    except ValueError as e:
        return f"Error: {e}"
    except OSError as e:
        return f"Error executing {name}: {e}"
