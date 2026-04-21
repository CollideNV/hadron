"""Agent tool definitions and execution engine.

Handles tool definition building, safe file I/O, command validation,
environment scrubbing, and tool dispatch.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import structlog

from hadron.config.limits import MAX_COMMAND_OUTPUT_CHARS, MAX_READ_FILE_CHARS
from hadron.security.validators import sanitize_agent_command, validate_agent_command
from hadron.utils.text import truncate
from hadron.utils.venv import find_worktree_venv

logger = structlog.stdlib.get_logger(__name__)

# Env var prefixes / keys stripped from agent subprocess environments.
_SCRUB_PREFIXES = ("HADRON_", "ANTHROPIC_", "OPENAI_", "GEMINI_", "GITHUB_", "AZURE_", "AWS_")
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
    "delete_file": {
        "name": "delete_file",
        "description": "Delete a file within the working directory. Path is relative to the working directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to delete"},
            },
            "required": ["path"],
        },
    },
}


def make_tools(allowed: list[str], working_dir: str | None) -> list[dict]:
    """Build Anthropic tool definitions for the allowed tool set."""
    return [_ALL_TOOL_DEFS[name] for name in allowed if name in _ALL_TOOL_DEFS]


def make_tools_openai(allowed: list[str], working_dir: str | None) -> list[dict]:
    """Build OpenAI-format tool definitions for the allowed tool set.

    Returns a list of ``{"type": "function", "function": {...}}`` dicts.
    """
    result = []
    for name in allowed:
        defn = _ALL_TOOL_DEFS.get(name)
        if defn is None:
            continue
        result.append({
            "type": "function",
            "function": {
                "name": defn["name"],
                "description": defn["description"],
                "parameters": defn["input_schema"],
            },
        })
    return result


def make_tools_gemini(allowed: list[str], working_dir: str | None) -> list[dict]:
    """Build Gemini-format function declarations for the allowed tool set.

    Returns a list of dicts suitable for ``Tool(function_declarations=[...])``.
    """
    result = []
    for name in allowed:
        defn = _ALL_TOOL_DEFS.get(name)
        if defn is None:
            continue
        result.append({
            "name": defn["name"],
            "description": defn["description"],
            "parameters": defn["input_schema"],
        })
    return result


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


_INSTALL_TRIGGERS: dict[str, list[str]] = {
    "package.json": ["npm", "install"],
    "pyproject.toml": ["pip", "install", "-e", ".", "--quiet"],
    "requirements.txt": ["pip", "install", "-r", "requirements.txt", "--quiet"],
}


async def _execute_write_file(working_dir: str, input_data: dict[str, Any]) -> str:
    """Write content to a file, creating parent directories as needed.

    Auto-runs dependency install when a manifest file is written.
    """
    path = safe_resolve(working_dir, input_data["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(input_data["content"])
    msg = f"File written: {input_data['path']}"

    filename = path.name
    if filename in _INSTALL_TRIGGERS:
        install_cmd = list(_INSTALL_TRIGGERS[filename])
        install_dir = str(path.parent)
        # Use the worktree venv's pip instead of the system/shared pip
        if install_cmd[0] == "pip":
            venv_path = find_worktree_venv(install_dir)
            if venv_path:
                install_cmd[0] = os.path.join(venv_path, "bin", "pip")
        logger.info("auto_install_deps", manifest=filename, install_dir=install_dir)
        proc = await asyncio.create_subprocess_exec(
            *install_cmd,
            cwd=install_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
            if proc.returncode == 0:
                msg += f"\n(auto-installed {filename} dependencies)"
            else:
                output = stdout.decode(errors="replace")[-300:]
                msg += f"\n(dependency install failed, exit {proc.returncode}: {output})"
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            msg += "\n(dependency install timed out)"

    return msg


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
    cmd = sanitize_agent_command(cmd)
    if not validate_agent_command(cmd):
        return f"Error: Command rejected by safety filter: {cmd!r}"
    env = {**scrubbed_env(), "PYTHONDONTWRITEBYTECODE": "1"}
    # Use the worktree's .venv so agent code changes and deps are isolated
    venv_path = find_worktree_venv(working_dir)
    if venv_path:
        venv_bin = os.path.join(venv_path, "bin")
        env["PATH"] = venv_bin + os.pathsep + env.get("PATH", "")
        env["VIRTUAL_ENV"] = venv_path
    # Ensure node_modules/.bin is in PATH so npm scripts find binaries like vitest
    node_bin = os.path.join(working_dir, "node_modules", ".bin")
    if os.path.isdir(node_bin):
        env["PATH"] = node_bin + os.pathsep + env.get("PATH", "")
    # Also check common subdirs (e.g. frontend/)
    for child in ("frontend", "client", "web", "app"):
        child_bin = os.path.join(working_dir, child, "node_modules", ".bin")
        if os.path.isdir(child_bin):
            env["PATH"] = child_bin + os.pathsep + env.get("PATH", "")
    proc = await asyncio.create_subprocess_shell(
        cmd,
        cwd=working_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
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


def _execute_delete_file(working_dir: str, input_data: dict[str, Any]) -> str:
    """Delete a file within the working directory."""
    path = safe_resolve(working_dir, input_data["path"])
    if not path.is_file():
        return f"Error: File not found: {input_data['path']}"
    path.unlink()
    return f"File deleted: {input_data['path']}"


_TOOL_DISPATCH: dict[str, Any] = {
    "read_file": _execute_read_file,
    "write_file": _execute_write_file,
    "list_directory": _execute_list_directory,
    "run_command": _execute_run_command,
    "delete_file": _execute_delete_file,
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
