"""Claude agent backend — tool-use loop using the Anthropic SDK directly."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator

import anthropic

from hadron.agent.base import AgentEvent, AgentResult, AgentTask

logger = logging.getLogger(__name__)

# Env var prefixes / keys stripped from agent subprocess environments.
_SCRUB_PREFIXES = ("HADRON_", "ANTHROPIC_", "OPENAI_", "GITHUB_", "AZURE_", "AWS_")
_SCRUB_KEYS = frozenset({
    "DATABASE_URL", "REDIS_URL", "SECRET_KEY", "API_KEY",
    "GH_TOKEN", "GITLAB_TOKEN", "BITBUCKET_TOKEN",
})


def _scrubbed_env() -> dict[str, str]:
    """Return a copy of os.environ with secrets stripped.

    Keeps PATH and other non-sensitive vars so tools like git/pytest still work.
    """
    return {
        k: v
        for k, v in os.environ.items()
        if k not in _SCRUB_KEYS and not k.startswith(_SCRUB_PREFIXES)
    }


# Per-model cost per million tokens: (input, output)
_MODEL_COSTS: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5-20251001": (0.80, 4.00),
    "claude-sonnet-4-20250514": (3.00, 15.00),
    "claude-opus-4-20250514": (15.00, 75.00),
}
# Fallback for unknown models (use Sonnet pricing)
_DEFAULT_COST = (3.00, 15.00)

# Rate limit retry settings
_RATE_LIMIT_MAX_RETRIES = 5
_RATE_LIMIT_BASE_WAIT = 60  # seconds


def _compute_model_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Compute USD cost for a given model and token counts."""
    cost_in, cost_out = _MODEL_COSTS.get(model, _DEFAULT_COST)
    return (input_tokens * cost_in + output_tokens * cost_out) / 1_000_000


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


def _safe_resolve(working_dir: str, user_path: str) -> Path:
    """Resolve a user-provided path and ensure it stays within working_dir.

    Raises ValueError if the resolved path escapes the working directory.
    """
    root = Path(working_dir).resolve()
    resolved = (root / user_path).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(
            f"Path escapes working directory: {user_path}"
        )
    return resolved


async def _execute_tool(
    name: str, input_data: dict[str, Any], working_dir: str
) -> str:
    """Execute a tool call and return the result string."""
    try:
        if name == "read_file":
            path = _safe_resolve(working_dir, input_data["path"])
            if not path.is_file():
                return f"Error: File not found: {input_data['path']}"
            content = path.read_text()
            if len(content) > 100_000:
                return content[:100_000] + "\n... (truncated)"
            return content

        elif name == "write_file":
            path = _safe_resolve(working_dir, input_data["path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(input_data["content"])
            return f"File written: {input_data['path']}"

        elif name == "list_directory":
            dir_path = _safe_resolve(working_dir, input_data.get("path", "."))
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
                env={**_scrubbed_env(), "PYTHONDONTWRITEBYTECODE": "1"},
            )
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return "Error: Command timed out after 120s (process killed)"
            output = stdout.decode(errors="replace")
            if len(output) > 50_000:
                output = output[:50_000] + "\n... (truncated)"
            return f"Exit code: {proc.returncode}\n{output}"

        else:
            return f"Error: Unknown tool: {name}"
    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error executing {name}: {e}"


def _serialize_messages(msgs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert messages to JSON-serializable format."""
    result = []
    for msg in msgs:
        entry: dict[str, Any] = {"role": msg["role"]}
        content = msg.get("content")
        if isinstance(content, str):
            entry["content"] = content
        elif isinstance(content, list):
            serialized = []
            for item in content:
                if isinstance(item, dict):
                    serialized.append(item)
                elif hasattr(item, "type"):
                    if item.type == "text":
                        serialized.append({"type": "text", "text": item.text})
                    elif item.type == "tool_use":
                        serialized.append({
                            "type": "tool_use", "id": item.id,
                            "name": item.name, "input": item.input,
                        })
                else:
                    serialized.append(str(item))
            entry["content"] = serialized
        else:
            entry["content"] = str(content) if content else ""
        result.append(entry)
    return result


@dataclass
class _PhaseResult:
    """Internal result from a single phase."""

    output: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    tool_calls: list[dict[str, Any]]
    conversation: list[dict[str, Any]]
    round_count: int


class ClaudeAgentBackend:
    """Agent backend using the Anthropic Messages API with a tool-use loop.

    Supports three-phase execution: Explore (read-only) -> Plan (single call) -> Act (full tools).
    Phases are controlled by task.explore_model and task.plan_model — empty string skips the phase.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY", ""),
        )

    async def execute(self, task: AgentTask) -> AgentResult:
        """Run the agent's tool-use loop to completion.

        If explore_model and/or plan_model are set, runs a three-phase pipeline:
        1. Explore (Haiku): read-only tool loop to gather codebase context
        2. Plan (Opus): single API call to produce an implementation plan
        3. Act (Sonnet): full tool loop to execute the plan

        If neither is set, falls back to the original single-phase behaviour.
        """
        total_input = 0
        total_output = 0
        total_cost = 0.0
        all_tool_calls: list[dict[str, Any]] = []
        all_conversations: list[dict[str, Any]] = []
        total_rounds = 0
        exploration_summary = ""
        plan_text = ""

        # --- PHASE 1: Explore (read-only tools, typically Haiku) ---
        if task.explore_model:
            if task.on_event:
                await task.on_event("phase_started", {
                    "phase": "explore", "model": task.explore_model,
                })

            explore_result = await self._run_tool_loop(
                model=task.explore_model,
                system_prompt=self._build_explore_system(task),
                user_prompt=task.user_prompt,
                tools=_make_tools(task.explore_tools, task.working_directory),
                working_dir=task.working_directory or ".",
                max_rounds=task.explore_max_rounds,
                max_tokens=task.max_tokens,
                on_event=task.on_event,
                phase="explore",
            )
            exploration_summary = explore_result.output
            total_input += explore_result.input_tokens
            total_output += explore_result.output_tokens
            total_cost += explore_result.cost_usd
            all_tool_calls.extend(explore_result.tool_calls)
            all_conversations.extend(explore_result.conversation)
            total_rounds += explore_result.round_count

            if task.on_event:
                await task.on_event("phase_completed", {
                    "phase": "explore",
                    "model": task.explore_model,
                    "summary_length": len(exploration_summary),
                    "rounds": explore_result.round_count,
                    "input_tokens": explore_result.input_tokens,
                    "output_tokens": explore_result.output_tokens,
                })

            logger.info(
                "Explore phase complete: %d rounds, %d input tokens, summary=%d chars",
                explore_result.round_count, explore_result.input_tokens,
                len(exploration_summary),
            )

        # --- PHASE 2: Plan (single call, no tools, typically Opus) ---
        if task.plan_model:
            if task.on_event:
                await task.on_event("phase_started", {
                    "phase": "plan", "model": task.plan_model,
                })

            plan_result = await self._run_plan_call(
                model=task.plan_model,
                system_prompt=self._build_plan_system(task),
                user_prompt=self._build_plan_user(task, exploration_summary),
                max_tokens=task.max_tokens,
            )
            plan_text = plan_result.output
            total_input += plan_result.input_tokens
            total_output += plan_result.output_tokens
            total_cost += plan_result.cost_usd
            all_conversations.extend(plan_result.conversation)

            if task.on_event:
                await task.on_event("phase_completed", {
                    "phase": "plan",
                    "model": task.plan_model,
                    "plan_length": len(plan_text),
                    "input_tokens": plan_result.input_tokens,
                    "output_tokens": plan_result.output_tokens,
                })

            logger.info(
                "Plan phase complete: %d input tokens, plan=%d chars",
                plan_result.input_tokens, len(plan_text),
            )

        # --- PHASE 3: Act (full tools, typically Sonnet) ---
        if task.on_event and (task.explore_model or task.plan_model):
            await task.on_event("phase_started", {
                "phase": "act", "model": task.model,
            })

        act_user_prompt = self._build_act_user(task, exploration_summary, plan_text)
        act_result = await self._run_tool_loop(
            model=task.model,
            system_prompt=task.system_prompt,
            user_prompt=act_user_prompt,
            tools=_make_tools(task.allowed_tools, task.working_directory),
            working_dir=task.working_directory or ".",
            max_rounds=task.max_tool_rounds,
            max_tokens=task.max_tokens,
            on_event=task.on_event,
            on_tool_call=task.on_tool_call,
            nudge_poll=task.nudge_poll,
            phase="act",
        )
        total_input += act_result.input_tokens
        total_output += act_result.output_tokens
        total_cost += act_result.cost_usd
        all_tool_calls.extend(act_result.tool_calls)
        all_conversations.extend(act_result.conversation)
        total_rounds += act_result.round_count

        if task.on_event and (task.explore_model or task.plan_model):
            await task.on_event("phase_completed", {
                "phase": "act",
                "model": task.model,
                "rounds": act_result.round_count,
                "input_tokens": act_result.input_tokens,
                "output_tokens": act_result.output_tokens,
            })

        return AgentResult(
            output=act_result.output,
            input_tokens=total_input,
            output_tokens=total_output,
            cost_usd=total_cost,
            tool_calls=all_tool_calls,
            conversation=all_conversations,
            round_count=total_rounds,
        )

    # ------------------------------------------------------------------
    # Phase helpers
    # ------------------------------------------------------------------

    def _build_explore_system(self, task: AgentTask) -> str:
        """Build the system prompt for the explore phase."""
        from hadron.agent.prompt import PromptComposer, _load_template
        try:
            explorer_template = _load_template("explorer")
        except FileNotFoundError:
            explorer_template = (
                "You are a codebase explorer. Use list_directory and read_file "
                "to understand the project structure. Produce a structured summary. "
                "Do NOT write files or run commands."
            )
        return explorer_template

    def _build_plan_system(self, task: AgentTask) -> str:
        """Build the system prompt for the plan phase."""
        from hadron.agent.prompt import _load_template
        try:
            planner_template = _load_template("planner")
        except FileNotFoundError:
            planner_template = (
                "You are an implementation planner. Analyse the exploration results "
                "and produce a concrete implementation plan."
            )
        # Include the original role system prompt as context for the planner
        return f"{planner_template}\n\n## Original Role Instructions\n\n{task.system_prompt}"

    def _build_plan_user(self, task: AgentTask, exploration_summary: str) -> str:
        """Build the user prompt for the plan phase."""
        parts = []
        if exploration_summary:
            parts.append(f"## Exploration Summary\n\n{exploration_summary}")
        parts.append(f"## Original Task\n\n{task.user_prompt}")
        return "\n\n".join(parts)

    def _build_act_user(self, task: AgentTask, exploration_summary: str, plan_text: str) -> str:
        """Build the user prompt for the act phase.

        If no explore/plan phases ran, returns the original user prompt unchanged
        for backwards compatibility.
        """
        if not exploration_summary and not plan_text:
            return task.user_prompt

        parts = []
        if plan_text:
            parts.append(f"## Implementation Plan\n\n{plan_text}")
        if exploration_summary:
            parts.append(f"## Codebase Context (from exploration)\n\n{exploration_summary}")
        parts.append(f"## Original Task\n\n{task.user_prompt}")
        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Core API call helpers
    # ------------------------------------------------------------------

    async def _run_tool_loop(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict],
        working_dir: str,
        max_rounds: int,
        max_tokens: int,
        on_event: Any = None,
        on_tool_call: Any = None,
        nudge_poll: Any = None,
        phase: str = "",
    ) -> _PhaseResult:
        """Run the tool-use loop for a single phase. Core reusable engine."""
        messages: list[dict[str, Any]] = [{"role": "user", "content": user_prompt}]
        total_input = 0
        total_output = 0
        all_tool_calls: list[dict[str, Any]] = []
        final_text = ""
        round_num = 0

        for round_num in range(max_rounds):
            # API call with rate-limit retry
            for attempt in range(_RATE_LIMIT_MAX_RETRIES):
                try:
                    response = await self._client.messages.create(
                        model=model,
                        max_tokens=max_tokens,
                        system=system_prompt,
                        tools=tools,
                        messages=messages,
                    )
                    break
                except anthropic.RateLimitError as e:
                    if attempt == _RATE_LIMIT_MAX_RETRIES - 1:
                        raise
                    wait = _RATE_LIMIT_BASE_WAIT * (attempt + 1)
                    logger.warning(
                        "Rate limited [%s] (attempt %d/%d), waiting %ds: %s",
                        phase, attempt + 1, _RATE_LIMIT_MAX_RETRIES, wait, e,
                    )
                    if on_event:
                        await on_event("output", {
                            "text": f"[Rate limited ({phase}) — waiting {wait}s before retrying...]",
                            "round": round_num,
                        })
                    await asyncio.sleep(wait)

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
                if on_event:
                    await on_event("output", {"text": final_text, "round": round_num})

            # If no tool calls, we're done
            if not tool_uses or response.stop_reason == "end_turn" and not tool_uses:
                break

            # Execute tools and build the response
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for tu in tool_uses:
                logger.info("[%s] Tool call: %s(%s)", phase, tu.name, json.dumps(tu.input)[:200])
                all_tool_calls.append({"name": tu.name, "input": tu.input})

                if on_event:
                    await on_event("tool_call", {
                        "tool": tu.name, "input": tu.input, "round": round_num,
                    })

                result_text = await _execute_tool(tu.name, tu.input, working_dir)

                if on_event:
                    await on_event("tool_result", {
                        "tool": tu.name, "result": result_text[:10_000], "round": round_num,
                    })

                if on_tool_call and not on_event:
                    await on_tool_call(tu.name, tu.input, result_text[:5000])

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": result_text,
                })

            messages.append({"role": "user", "content": tool_results})

            if response.stop_reason == "end_turn":
                break

            # Check for nudge between rounds
            if nudge_poll:
                nudge = await nudge_poll()
                if nudge:
                    if on_event:
                        await on_event("nudge", {"text": nudge})
                    messages.append({"role": "user", "content": nudge})

        cost = _compute_model_cost(model, total_input, total_output)

        return _PhaseResult(
            output=final_text,
            input_tokens=total_input,
            output_tokens=total_output,
            cost_usd=cost,
            tool_calls=all_tool_calls,
            conversation=_serialize_messages(messages),
            round_count=round_num + 1 if messages else 0,
        )

    async def _run_plan_call(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
    ) -> _PhaseResult:
        """Single API call for the plan phase — no tools."""
        for attempt in range(_RATE_LIMIT_MAX_RETRIES):
            try:
                response = await self._client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                break
            except anthropic.RateLimitError as e:
                if attempt == _RATE_LIMIT_MAX_RETRIES - 1:
                    raise
                wait = _RATE_LIMIT_BASE_WAIT * (attempt + 1)
                logger.warning(
                    "Rate limited [plan] (attempt %d/%d), waiting %ds: %s",
                    attempt + 1, _RATE_LIMIT_MAX_RETRIES, wait, e,
                )
                await asyncio.sleep(wait)

        text = ""
        for block in response.content:
            if block.type == "text":
                text += block.text

        cost = _compute_model_cost(model, response.usage.input_tokens, response.usage.output_tokens)

        return _PhaseResult(
            output=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cost_usd=cost,
            tool_calls=[],
            conversation=_serialize_messages([
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": response.content},
            ]),
            round_count=1,
        )

    # ------------------------------------------------------------------
    # Streaming (unchanged — does not use three-phase yet)
    # ------------------------------------------------------------------

    async def stream(self, task: AgentTask) -> AsyncIterator[AgentEvent]:
        """Stream agent events. Yields events as they happen."""
        tools = _make_tools(task.allowed_tools, task.working_directory)
        messages: list[dict[str, Any]] = [{"role": "user", "content": task.user_prompt}]

        for round_num in range(task.max_tool_rounds):
            for attempt in range(_RATE_LIMIT_MAX_RETRIES):
                try:
                    response = await self._client.messages.create(
                        model=task.model,
                        max_tokens=task.max_tokens,
                        system=task.system_prompt,
                        tools=tools,
                        messages=messages,
                    )
                    break
                except anthropic.RateLimitError as e:
                    if attempt == _RATE_LIMIT_MAX_RETRIES - 1:
                        raise
                    wait = _RATE_LIMIT_BASE_WAIT * (attempt + 1)
                    logger.warning(
                        "Rate limited in stream (attempt %d/%d), waiting %ds: %s",
                        attempt + 1, _RATE_LIMIT_MAX_RETRIES, wait, e,
                    )
                    yield AgentEvent(
                        event_type="text_delta",
                        data={"text": f"[Rate limited — waiting {wait}s before retrying...]"},
                    )
                    await asyncio.sleep(wait)

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
                    data={"name": tu.name, "result": result_text[:5000]},
                )
            messages.append({"role": "user", "content": tool_results})

            if response.stop_reason == "end_turn":
                break

        yield AgentEvent(event_type="done", data={})
