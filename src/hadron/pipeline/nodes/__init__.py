"""Pipeline node helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Awaitable

from langgraph.types import RunnableConfig

from hadron.events.bus import EventBus
from hadron.models.events import EventType, PipelineEvent
from hadron.models.pipeline_state import PipelineState
from hadron.pipeline.nodes.context import NodeContext

# Re-export from sub-modules for backwards compatibility
from hadron.config.limits import MAX_CONTEXT_CHARS  # noqa: F401
from hadron.pipeline.nodes.json_extract import extract_json  # noqa: F401
from hadron.pipeline.nodes.files import gather_files, gather_changed_files  # noqa: F401
from hadron.pipeline.nodes.callbacks import (  # noqa: F401
    make_tool_call_emitter,
    make_agent_event_emitter,
    make_nudge_poller,
    store_conversation,
    emit_cost_update,
)
from hadron.pipeline.nodes.agent_run import AgentRunResult, run_agent  # noqa: F401

__all__ = [
    "NodeContext",
    "RepoInfo",
    "AgentRunResult",
    "extract_json",
    "pipeline_node",
    "run_agent",
    "gather_files",
    "gather_changed_files",
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
