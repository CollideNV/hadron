"""Shared tool definitions and execution logic for agent backends.

Every agent backend (Claude, Gemini, …) gives agents the same set of
tools (read_file, write_file, list_directory, run_command).  This module
provides:
  - ``TOOL_DEFINITIONS``: canonical tool metadata (name + description +
    input schema) that can be translated into each SDK's format.
  - ``execute_tool()``: the actual implementation that runs a tool call.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Canonical tool definitions
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: dict[str, dict[str, Any]] = {
    "read_file": {
        "name": "read_file",
        "description": "Read the contents of a file. Path is relative to the working directory.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to read"},
            },
            "required": ["path"],
        },
    },
    "write_file": {
        "name": "write_file",
        "description": "Write content to a file. Creates parent directories if needed. Path is relative to the working directory.",
        "parameters": {
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
        "parameters": {
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
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
            },
            "required": ["command"],
        },
    },
}


def get_tool_definitions(allowed: list[str]) -> list[dict[str, Any]]:
    """Return tool definitions for *allowed* tool names."""
    return [TOOL_DEFINITIONS[name] for name in allowed if name in TOOL_DEFINITIONS]


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------


async def execute_tool(
    name: str, input_data: dict[str, Any], working_dir: str
) -> str:
    """Execute a tool call and return the result string."""
    try:
        if name == "read_file":
            path = Path(working_dir) / input_data["path"]
            if not path.is_file():
                return f"Error: File not found: {input_data['path']}"
            content = path.read_text()
            if len(content) > 100_000:
                return content[:100_000] + "\n... (truncated)"
            return content

        elif name == "write_file":
            path = Path(working_dir) / input_data["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(input_data["content"])
            return f"File written: {input_data['path']}"

        elif name == "list_directory":
            dir_path = Path(working_dir) / input_data.get("path", ".")
            if not dir_path.is_dir():
                return f"Error: Not a directory: {input_data.get('path', '.')}"
            entries = sorted(dir_path.iterdir())
            lines = []
            for e in entries[:200]:
                prefix = "d " if e.is_dir() else "f "
                lines.append(f"{prefix}{e.name}")
            return "\n".join(lines) if lines else "(empty directory)"

        elif name == "run_command":
            proc = await asyncio.create_subprocess_shell(
                input_data["command"],
                cwd=working_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
            output = stdout.decode(errors="replace")
            if len(output) > 50_000:
                output = output[:50_000] + "\n... (truncated)"
            return f"Exit code: {proc.returncode}\n{output}"

        else:
            return f"Error: Unknown tool: {name}"
    except Exception as e:
        return f"Error executing {name}: {e}"
