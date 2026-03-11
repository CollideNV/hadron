"""Pipeline node helpers."""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Awaitable

import redis.asyncio as aioredis

from hadron.agent.base import AgentResult, AgentTask, OnAgentEvent, OnToolCall
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
        @functools.wraps(fn)
        async def wrapper(
            state: PipelineState, config: Any,
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

        # Remove __wrapped__ so inspect.signature() sees the wrapper's
        # (state, config) signature, not the inner fn's (state, ctx, cr_id).
        # LangGraph uses signature inspection to decide how to call nodes.
        del wrapper.__wrapped__

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


# ---------------------------------------------------------------------------
# Event callback factories
# ---------------------------------------------------------------------------


def make_tool_call_emitter(
    event_bus: Any, cr_id: str, stage: str, role: str, repo: str = "",
) -> OnToolCall:
    """Create an on_tool_call callback that emits AGENT_TOOL_CALL events."""

    async def _on_tool_call(
        tool_name: str, tool_input: dict[str, Any], result_snippet: str,
    ) -> None:
        if event_bus:
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
    event_bus: Any, cr_id: str, stage: str, role: str, repo: str = "",
) -> OnAgentEvent:
    """Create an on_event callback that emits rich agent events."""

    async def _on_event(event_type: str, data: dict[str, Any]) -> None:
        if not event_bus:
            return
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
        elif event_type == "nudge":
            await event_bus.emit(PipelineEvent(
                cr_id=cr_id,
                event_type=EventType.AGENT_NUDGE,
                stage=stage,
                data={"role": role, "repo": repo, "text": data["text"]},
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
    event_bus: Any, cr_id: str, stage: str, result: AgentResult, prior_cost: float = 0.0,
) -> None:
    """Emit a COST_UPDATE event after an agent execution."""
    if event_bus:
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
