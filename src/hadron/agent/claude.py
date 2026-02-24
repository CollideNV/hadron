"""Claude agent backend — tool-use loop using the Anthropic SDK directly."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, AsyncIterator

import anthropic

from hadron.agent.base import AgentEvent, AgentResult, AgentTask

logger = logging.getLogger(__name__)

# Cost per million tokens (Claude Sonnet 4)
_COST_PER_M_INPUT = 3.00
_COST_PER_M_OUTPUT = 15.00


def _make_tools(allowed: list[str], working_dir: str | None) -> list[dict]:
    """Build Anthropic tool definitions for the allowed tool set."""
    all_tools = {
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
            "description": "Write content to a file. Creates parent directories if needed. Path is relative to the working directory.",
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
    return [all_tools[name] for name in allowed if name in all_tools]


async def _execute_tool(
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


class ClaudeAgentBackend:
    """Agent backend using the Anthropic Messages API with a tool-use loop.

    Flow: send message → if tool_use in response → execute tool → send result → repeat.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY", ""),
        )

    async def execute(self, task: AgentTask) -> AgentResult:
        """Run the agent's tool-use loop to completion."""
        tools = _make_tools(task.allowed_tools, task.working_directory)
        messages: list[dict[str, Any]] = [{"role": "user", "content": task.user_prompt}]

        total_input = 0
        total_output = 0
        all_tool_calls: list[dict[str, Any]] = []
        final_text = ""

        for round_num in range(task.max_tool_rounds):
            response = await self._client.messages.create(
                model=task.model,
                max_tokens=task.max_tokens,
                system=task.system_prompt,
                tools=tools,
                messages=messages,
            )

            total_input += response.usage.input_tokens
            total_output += response.usage.output_tokens

            # Collect text and tool use blocks
            text_parts = []
            tool_uses = []
            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "tool_use":
                    tool_uses.append(block)

            if text_parts:
                final_text = "\n".join(text_parts)

            # If no tool calls, we're done
            if not tool_uses or response.stop_reason == "end_turn" and not tool_uses:
                break

            # Execute tools and build the response
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for tu in tool_uses:
                logger.info("Tool call: %s(%s)", tu.name, json.dumps(tu.input)[:200])
                all_tool_calls.append({"name": tu.name, "input": tu.input})

                result_text = await _execute_tool(
                    tu.name, tu.input, task.working_directory or "."
                )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": result_text,
                })

            messages.append({"role": "user", "content": tool_results})

            if response.stop_reason == "end_turn":
                break

        cost = (total_input * _COST_PER_M_INPUT + total_output * _COST_PER_M_OUTPUT) / 1_000_000

        return AgentResult(
            output=final_text,
            input_tokens=total_input,
            output_tokens=total_output,
            cost_usd=cost,
            tool_calls=all_tool_calls,
        )

    async def stream(self, task: AgentTask) -> AsyncIterator[AgentEvent]:
        """Stream agent events. Yields events as they happen."""
        # For MVP, we do the tool loop and yield events after each round
        tools = _make_tools(task.allowed_tools, task.working_directory)
        messages: list[dict[str, Any]] = [{"role": "user", "content": task.user_prompt}]

        for round_num in range(task.max_tool_rounds):
            response = await self._client.messages.create(
                model=task.model,
                max_tokens=task.max_tokens,
                system=task.system_prompt,
                tools=tools,
                messages=messages,
            )

            text_parts = []
            tool_uses = []
            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
                    yield AgentEvent(event_type="text_delta", data={"text": block.text})
                elif block.type == "tool_use":
                    tool_uses.append(block)
                    yield AgentEvent(
                        event_type="tool_use",
                        data={"name": block.name, "input": block.input},
                    )

            if not tool_uses or response.stop_reason == "end_turn" and not tool_uses:
                break

            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for tu in tool_uses:
                result_text = await _execute_tool(
                    tu.name, tu.input, task.working_directory or "."
                )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": result_text,
                })
                yield AgentEvent(
                    event_type="tool_result",
                    data={"name": tu.name, "result": result_text[:500]},
                )
            messages.append({"role": "user", "content": tool_results})

            if response.stop_reason == "end_turn":
                break

        yield AgentEvent(event_type="done", data={})
