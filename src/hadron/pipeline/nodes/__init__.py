"""Pipeline node helpers."""

from __future__ import annotations

import functools
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Awaitable

import redis.asyncio as aioredis
from langgraph.types import RunnableConfig

from hadron.agent.base import AgentCallbacks, AgentResult, AgentTask, OnAgentEvent, OnToolCall, PhaseConfig
from hadron.config.limits import MAX_CONTEXT_CHARS
from hadron.events.bus import EventBus
from hadron.models.events import EventType, PipelineEvent
from hadron.models.pipeline_state import PipelineState
from hadron.pipeline.nodes.context import NodeContext

# Re-export NodeContext so nodes can do: from hadron.pipeline.nodes import NodeContext
__all__ = [
    "NodeContext",
    "RepoInfo",
    "AgentRunResult",
    "extract_json",
    "pipeline_node",
    "run_agent",
    "gather_files",
    "make_tool_call_emitter",
    "make_agent_event_emitter",
    "make_nudge_poller",
    "store_conversation",
    "emit_cost_update",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Decorator — eliminates boilerplate shared by every pipeline node
# ---------------------------------------------------------------------------


def pipeline_node(stage: str) -> Callable:
    """Decorator that handles common pipeline node ceremony.

    Wraps a node function to automatically:
      1. Extract ``NodeContext`` and ``cr_id`` from LangGraph's state/config.
      2. Emit a ``STAGE_ENTERED`` event.
      3. Catch unhandled exceptions → log, emit error event, return *paused*.

    The decorated function's signature changes from
    ``(state, config) -> dict`` to ``(state, ctx, cr_id) -> dict``,
    while the outer LangGraph-facing signature stays ``(state, config)``.
    """

    def decorator(
        fn: Callable[..., Awaitable[dict[str, Any]]],
    ) -> Callable[..., Awaitable[dict[str, Any]]]:
        async def wrapper(
            state: PipelineState, config: RunnableConfig,
        ) -> dict[str, Any]:
            ctx = NodeContext.from_config(config)
            cr_id = state["cr_id"]

            await ctx.event_bus.emit(PipelineEvent(
                cr_id=cr_id, event_type=EventType.STAGE_ENTERED, stage=stage,
            ))

            try:
                return await fn(state, ctx, cr_id)
            except Exception as exc:
                logger.exception(
                    "%s node crashed (CR %s): %s", stage, cr_id, exc,
                )
                await ctx.event_bus.emit(PipelineEvent(
                    cr_id=cr_id,
                    event_type=EventType.STAGE_COMPLETED,
                    stage=stage,
                    data={"error": str(exc)},
                ))
                return {
                    "current_stage": stage,
                    "status": "paused",
                    "error": f"{stage} node failed: {exc}",
                    "stage_history": [
                        {"stage": stage, "status": "error", "error": str(exc)},
                    ],
                }

        # Copy metadata but NOT __wrapped__/__annotations__ — LangGraph uses
        # inspect.signature() which follows __wrapped__, and the inner fn has
        # a different (state, ctx, cr_id) signature that confuses LangGraph's
        # config injection.
        wrapper.__name__ = fn.__name__
        wrapper.__qualname__ = fn.__qualname__
        wrapper.__doc__ = fn.__doc__
        wrapper.__module__ = fn.__module__
        return wrapper

    return decorator


@dataclass
class RepoInfo:
    """Common repo fields extracted from PipelineState."""

    repo_name: str
    worktree_path: str
    default_branch: str
    test_command: str
    languages: list[str]
    test_commands: list[str]
    agents_md: str
    raw: dict[str, Any]

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> RepoInfo:
        repo = state.get("repo", {})
        repo_name = repo.get("repo_name", "")
        if not repo_name:
            raise ValueError(
                "PipelineState['repo']['repo_name'] is missing or empty — "
                "cannot proceed without a repo name"
            )
        return cls(
            repo_name=repo_name,
            worktree_path=repo.get("worktree_path", ""),
            default_branch=repo.get("default_branch", "main"),
            test_command=(repo.get("test_commands") or ["pytest"])[0],
            languages=repo.get("languages", []),
            test_commands=repo.get("test_commands", []),
            agents_md=repo.get("agents_md", ""),
            raw=repo,
        )


# ---------------------------------------------------------------------------
# Shared JSON extraction from LLM output
# ---------------------------------------------------------------------------


def extract_json(text: str, *, context: str = "") -> dict[str, Any] | None:
    """Extract a JSON object from LLM text output.

    Tries multiple strategies in order:
      1. ```json ... ``` fenced block
      2. ``` ... ``` generic fenced block
      3. First ``{`` to last ``}`` substring
      4. Raw text as-is

    Returns the parsed dict, or None if all strategies fail.
    Logs the failure with *context* for debugging.
    """
    strategies: list[tuple[str, Any]] = [
        ("json-fence", lambda t: t.split("```json")[1].split("```")[0] if "```json" in t else None),
        ("generic-fence", lambda t: t.split("```")[1].split("```")[0] if "```" in t else None),
        ("brace-scan", lambda t: t[t.index("{"):t.rindex("}") + 1] if "{" in t else None),
        ("raw", lambda t: t),
    ]
    for name, extract in strategies:
        try:
            candidate = extract(text)
            if candidate:
                return json.loads(candidate.strip())
        except (json.JSONDecodeError, IndexError, ValueError):
            continue
    logger.error("Failed to extract JSON from LLM output (%s): %.500s", context, text)
    return None


# ---------------------------------------------------------------------------
# Shared file gathering utility (moved from tdd.py)
# ---------------------------------------------------------------------------

def gather_files(worktree: str, pattern: str) -> str:
    """Read files matching glob pattern and return formatted content."""
    base = Path(worktree)
    parts: list[str] = []
    total = 0
    for path in sorted(base.glob(pattern)):
        if not path.is_file():
            continue
        content = path.read_text(errors="replace")
        rel = path.relative_to(base)
        entry = f"### {rel}\n\n```\n{content}\n```"
        if total + len(entry) > MAX_CONTEXT_CHARS:
            parts.append(f"\n... ({pattern}: remaining files truncated)")
            break
        parts.append(entry)
        total += len(entry)
    return "\n\n".join(parts)


def gather_changed_files(worktree: str, pattern: str, default_branch: str = "main") -> str:
    """Read files matching glob pattern that were added or modified in this branch.

    Uses ``git diff`` against the merge-base with the default branch to scope
    to files changed by this CR, avoiding injection of unrelated pre-existing
    files.  Also includes uncommitted (staged + unstaged + untracked) changes.

    Uses two passes: (1) git to get all changed/untracked files, (2) pathlib
    glob to get files matching the pattern, then intersects the two sets so
    only changed files that match the pattern are included.
    """
    import subprocess

    base = Path(worktree)
    changed: set[str] = set()

    def _lines(result: subprocess.CompletedProcess[str]) -> list[str]:
        return [l.strip() for l in result.stdout.splitlines() if l.strip()]

    try:
        # 1. Committed changes since branching from default branch
        merge_base = subprocess.run(
            ["git", "merge-base", default_branch, "HEAD"],
            cwd=worktree, capture_output=True, text=True, timeout=10,
        )
        if merge_base.returncode == 0 and merge_base.stdout.strip():
            committed = subprocess.run(
                ["git", "diff", "--name-only", "--diff-filter=ACMR",
                 merge_base.stdout.strip(), "HEAD"],
                cwd=worktree, capture_output=True, text=True, timeout=10,
            )
            changed.update(_lines(committed))

        # 2. Uncommitted changes to tracked files (staged + unstaged)
        uncommitted = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=ACMR", "HEAD"],
            cwd=worktree, capture_output=True, text=True, timeout=10,
        )
        changed.update(_lines(uncommitted))

        # 3. Untracked new files (written by agent but never committed)
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=worktree, capture_output=True, text=True, timeout=10,
        )
        changed.update(_lines(untracked))

    except (subprocess.SubprocessError, OSError):
        logger.warning("git commands failed in gather_changed_files; returning empty")
        return ""

    if not changed:
        return ""

    # Use pathlib glob (handles ** correctly) then intersect with changed set
    matching = {str(p.relative_to(base)) for p in base.glob(pattern) if p.is_file()}
    matched = sorted(changed & matching)

    if not matched:
        return ""

    parts: list[str] = []
    total = 0
    for rel in matched:
        path = base / rel
        if not path.is_file():
            continue
        content = path.read_text(errors="replace")
        entry = f"### {rel}\n\n```\n{content}\n```"
        if total + len(entry) > MAX_CONTEXT_CHARS:
            parts.append(f"\n... ({pattern}: remaining files truncated)")
            break
        parts.append(entry)
        total += len(entry)
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Event callback factories
# ---------------------------------------------------------------------------


def make_tool_call_emitter(
    event_bus: EventBus, cr_id: str, stage: str, role: str, repo: str = "",
) -> OnToolCall:
    """Create an on_tool_call callback that emits AGENT_TOOL_CALL events."""

    async def _on_tool_call(
        tool_name: str, tool_input: dict[str, Any], result_snippet: str,
    ) -> None:
        await event_bus.emit(PipelineEvent(
                cr_id=cr_id,
                event_type=EventType.AGENT_TOOL_CALL,
                stage=stage,
                data={
                    "role": role,
                    "repo": repo,
                    "tool": tool_name,
                    "input": {k: v[:2000] if isinstance(v, str) else v for k, v in tool_input.items()},
                    "result_snippet": result_snippet[:5000],
                },
            ))

    return _on_tool_call


def make_agent_event_emitter(
    event_bus: EventBus, cr_id: str, stage: str, role: str, repo: str = "",
) -> OnAgentEvent:
    """Create an on_event callback that emits rich agent events."""

    async def _on_event(event_type: str, data: dict[str, Any]) -> None:
        if event_type == "output":
            await event_bus.emit(PipelineEvent(
                cr_id=cr_id,
                event_type=EventType.AGENT_OUTPUT,
                stage=stage,
                data={"role": role, "repo": repo, "text": data["text"], "round": data.get("round", 0)},
            ))
        elif event_type == "tool_call":
            await event_bus.emit(PipelineEvent(
                cr_id=cr_id,
                event_type=EventType.AGENT_TOOL_CALL,
                stage=stage,
                data={
                    "role": role, "repo": repo,
                    "tool": data["tool"], "input": data["input"],
                    "round": data.get("round", 0), "type": "call",
                },
            ))
        elif event_type == "tool_result":
            await event_bus.emit(PipelineEvent(
                cr_id=cr_id,
                event_type=EventType.AGENT_TOOL_CALL,
                stage=stage,
                data={
                    "role": role, "repo": repo,
                    "tool": data["tool"], "result": data["result"][:10_000],
                    "round": data.get("round", 0), "type": "result",
                },
            ))
        elif event_type == "prompt":
            await event_bus.emit(PipelineEvent(
                cr_id=cr_id,
                event_type=EventType.AGENT_PROMPT,
                stage=stage,
                data={"role": role, "repo": repo, "text": data["text"][:5000]},
            ))
        elif event_type == "nudge":
            await event_bus.emit(PipelineEvent(
                cr_id=cr_id,
                event_type=EventType.AGENT_NUDGE,
                stage=stage,
                data={"role": role, "repo": repo, "text": data["text"]},
            ))
        elif event_type == "phase_started":
            await event_bus.emit(PipelineEvent(
                cr_id=cr_id,
                event_type=EventType.PHASE_STARTED,
                stage=stage,
                data={"role": role, "repo": repo, **data},
            ))
        elif event_type == "phase_completed":
            await event_bus.emit(PipelineEvent(
                cr_id=cr_id,
                event_type=EventType.PHASE_COMPLETED,
                stage=stage,
                data={"role": role, "repo": repo, **data},
            ))

    return _on_event


def make_nudge_poller(
    redis_client: aioredis.Redis, cr_id: str, role: str,
) -> Callable[[], Awaitable[str | None]]:
    """Create an async callable that atomically gets+deletes a nudge for a specific agent role."""

    async def _poll() -> str | None:
        key = f"hadron:cr:{cr_id}:nudge:{role}"
        pipe = redis_client.pipeline()
        pipe.get(key)
        pipe.delete(key)
        results = await pipe.execute()
        value = results[0]
        if value is None:
            return None
        return value.decode() if isinstance(value, bytes) else value

    return _poll


async def store_conversation(
    redis_client: aioredis.Redis,
    cr_id: str,
    role: str,
    repo: str,
    conversation: list[dict[str, Any]],
) -> str:
    """Store agent conversation in Redis with 7-day TTL. Returns the key."""
    ts = int(time.time())
    key = f"hadron:cr:{cr_id}:conv:{role}:{repo}:{ts}"
    await redis_client.set(key, json.dumps(conversation, default=str), ex=604800)
    return key


async def emit_cost_update(
    event_bus: EventBus, cr_id: str, stage: str, result: AgentResult, prior_cost: float = 0.0,
) -> None:
    """Emit a COST_UPDATE event after an agent execution."""
    await event_bus.emit(PipelineEvent(
        cr_id=cr_id,
        event_type=EventType.COST_UPDATE,
        stage=stage,
        data={
            "delta_usd": result.cost_usd,
            "total_cost_usd": prior_cost + result.cost_usd,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
        },
    ))


# ---------------------------------------------------------------------------
# run_agent — unified agent execution with events + cost + conversation
# ---------------------------------------------------------------------------


@dataclass
class AgentRunResult:
    """Result from run_agent, wrapping AgentResult with conversation key."""

    result: AgentResult
    conversation_key: str = ""


async def run_agent(
    ctx: NodeContext,
    *,
    role: str,
    system_prompt: str,
    user_prompt: str,
    cr_id: str,
    stage: str,
    repo_name: str = "",
    working_directory: str = "",
    allowed_tools: list[str] | None = None,
    model: str | None = None,
    explore_model: str | None = None,
    plan_model: str | None = None,
    prior_cost: float = 0.0,
    loop_iteration: int = 0,
) -> AgentRunResult:
    """Run an agent with full event emission, cost tracking, and conversation storage.

    This replaces the repeated ceremony of:
        1. Build AgentTask with callbacks
        2. Emit AGENT_STARTED
        3. Execute agent
        4. Emit COST_UPDATE
        5. Store conversation
        6. Emit AGENT_COMPLETED
    """
    effective_model = model or ctx.model
    effective_explore = explore_model if explore_model is not None else ctx.explore_model
    effective_plan = plan_model if plan_model is not None else ctx.plan_model

    if allowed_tools is None:
        allowed_tools = ["read_file", "write_file", "list_directory", "run_command"]

    task = AgentTask(
        role=role,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        working_directory=working_directory,
        allowed_tools=allowed_tools,
        model=effective_model,
        phases=PhaseConfig(
            explore_model=effective_explore,
            plan_model=effective_plan,
        ),
        callbacks=AgentCallbacks(
            on_tool_call=make_tool_call_emitter(ctx.event_bus, cr_id, stage, role, repo_name),
            on_event=make_agent_event_emitter(ctx.event_bus, cr_id, stage, role, repo_name),
            nudge_poll=make_nudge_poller(ctx.redis, cr_id, role) if ctx.redis else None,
        ),
    )

    models_used = [m for m in [effective_explore, effective_plan, effective_model] if m]
    await ctx.event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.AGENT_STARTED, stage=stage,
            data={
                "role": role, "repo": repo_name,
                "model": effective_model,
                "explore_model": effective_explore,
                "plan_model": effective_plan,
                "models": models_used,
                "allowed_tools": allowed_tools,
                "loop_iteration": loop_iteration,
            },
        ))

    result = await ctx.agent_backend.execute(task)
    await emit_cost_update(ctx.event_bus, cr_id, stage, result, prior_cost)

    conv_key = ""
    if ctx.redis and result.conversation:
        conv_key = await store_conversation(ctx.redis, cr_id, role, repo_name, result.conversation)

    await ctx.event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.AGENT_COMPLETED, stage=stage,
            data={
                "role": role, "repo": repo_name,
                "model": effective_model,
                "output": result.output[:2000],
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "cost_usd": result.cost_usd,
                "tool_calls_count": len(result.tool_calls),
                "round_count": result.round_count,
                "conversation_key": conv_key,
                "loop_iteration": loop_iteration,
                "throttle_count": result.throttle_count,
                "throttle_seconds": result.throttle_seconds,
                "model_breakdown": result.model_breakdown,
            },
        ))

    return AgentRunResult(result=result, conversation_key=conv_key)
