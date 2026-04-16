"""Typed context for pipeline nodes — replaces untyped configurable dict extraction."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from langgraph.types import RunnableConfig

from hadron.agent.prompt import PromptComposer
from hadron.config.defaults import DEFAULT_MODEL, DEFAULT_WORKSPACE_DIR
from hadron.events.bus import EventBus, NoOpEventBus
from hadron.git.worktree import WorktreeManager

if TYPE_CHECKING:
    import redis.asyncio as aioredis

    from hadron.agent.base import AgentBackend
    from hadron.events.interventions import InterventionManager
    from hadron.pipeline.e2e_runner import E2ERunnerLifecycle


@dataclass
class NodeContext:
    """Typed access to infrastructure services available to pipeline nodes.

    Constructed once per node invocation via ``NodeContext.from_config(config)``.
    ``event_bus`` is always non-None (uses NoOpEventBus when no real bus is available),
    so callers never need ``if ctx.event_bus:`` guards.
    """

    event_bus: EventBus
    agent_backend: AgentBackend
    workspace_dir: str
    worktree_manager: WorktreeManager
    redis: aioredis.Redis | None
    model: str
    explore_model: str
    plan_model: str
    intervention_mgr: InterventionManager | None
    prompt_composer: PromptComposer
    stage_models: dict[str, dict] = field(default_factory=dict)
    default_backend: str = "claude"
    backend_pool: Any = None
    e2e_lifecycle: E2ERunnerLifecycle | None = None

    @classmethod
    def from_config(cls, config: RunnableConfig) -> NodeContext:
        """Extract a typed NodeContext from LangGraph's RunnableConfig."""
        configurable = config.get("configurable", {})
        workspace_dir = configurable.get("workspace_dir", DEFAULT_WORKSPACE_DIR)
        worktree_manager = configurable.get("worktree_manager") or WorktreeManager(workspace_dir)
        return cls(
            event_bus=configurable.get("event_bus") or NoOpEventBus(),
            agent_backend=configurable.get("agent_backend"),
            workspace_dir=workspace_dir,
            worktree_manager=worktree_manager,
            redis=configurable.get("redis"),
            model=configurable.get("model", DEFAULT_MODEL),
            explore_model=configurable.get("explore_model", ""),
            plan_model=configurable.get("plan_model", ""),
            intervention_mgr=configurable.get("intervention_manager"),
            prompt_composer=configurable.get("prompt_composer") or PromptComposer(),
            stage_models=configurable.get("stage_models", {}),
            default_backend=configurable.get("default_backend", "claude"),
            backend_pool=configurable.get("backend_pool"),
            e2e_lifecycle=configurable.get("e2e_lifecycle"),
        )
