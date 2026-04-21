"""Unified agent execution with events, cost tracking, and conversation storage."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import structlog

from hadron.agent.base import AgentCallbacks, AgentResult, AgentTask, OnAgentEvent, OnToolCall, PhaseConfig
from hadron.events.bus import EventBus
from hadron.models.events import EventType, PipelineEvent
from hadron.observability.logging import bind_contextvars
from hadron.observability.tracing import set_span_attributes, span
from hadron.pipeline.nodes.callbacks import (
    emit_cost_update,
    make_agent_event_emitter,
    make_nudge_poller,
    make_tool_call_emitter,
    store_conversation,
)
from hadron.pipeline.nodes.context import NodeContext

logger = structlog.stdlib.get_logger(__name__)

# Node-level retry for transient LLM outages (after per-call retries are exhausted)
_NODE_LEVEL_MAX_RETRIES = 3
_NODE_LEVEL_COOLDOWN_SECONDS = 120  # 2 minutes between node-level retries


def _is_transient_llm_error(exc: Exception) -> bool:
    """Check if an exception is a transient LLM API error worth retrying at node level."""
    # Anthropic transient errors
    try:
        import anthropic
        if isinstance(exc, (anthropic.RateLimitError, anthropic.InternalServerError)):
            return True
    except ImportError:
        pass

    # Google/Gemini transient errors
    try:
        from google.api_core import exceptions as google_exc
        if isinstance(exc, (google_exc.ResourceExhausted, google_exc.ServiceUnavailable, google_exc.InternalServerError)):
            return True
    except ImportError:
        pass

    # OpenAI transient errors
    try:
        import openai
        if isinstance(exc, (openai.RateLimitError, openai.InternalServerError)):
            return True
    except ImportError:
        pass

    # Catch-all: check error message for common transient patterns
    msg = str(exc).lower()
    return any(kw in msg for kw in ("503", "unavailable", "overloaded", "rate limit", "resource exhausted"))


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
    """Run an agent with full event emission, cost tracking, and conversation storage."""
    bind_contextvars(agent_role=role)

    # Per-stage model/backend lookup from DB settings (highest priority)
    stage_cfg = ctx.stage_models.get(stage, {}) if ctx.stage_models else {}
    act_cfg = stage_cfg.get("act") if stage_cfg else None
    explore_cfg = stage_cfg.get("explore") if stage_cfg else None
    plan_cfg = stage_cfg.get("plan") if stage_cfg else None

    # Model precedence: per-stage DB config > explicit kwarg > global ctx default
    effective_model = (act_cfg["model"] if act_cfg else None) or model or ctx.model
    effective_explore = (explore_cfg["model"] if explore_cfg else None) if explore_model is None else (explore_model if explore_model else ctx.explore_model)
    effective_plan = (plan_cfg["model"] if plan_cfg else None) if plan_model is None else (plan_model if plan_model else ctx.plan_model)

    # Backend selection: per-stage > default
    backend_name = (act_cfg.get("backend") if act_cfg else None) or ctx.default_backend
    effective_backend = ctx.backend_pool.get(backend_name) if ctx.backend_pool else ctx.agent_backend

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

    with span(f"agent.{role}", {"role": role, "stage": stage, "model": effective_model}) as s:
        # Node-level retry: if per-call retries are exhausted (transient LLM
        # outage persists beyond ~8 min), cool down and retry the entire agent
        # execution. This prevents pipeline pauses on temporary API outages.
        last_exc: Exception | None = None
        for node_attempt in range(_NODE_LEVEL_MAX_RETRIES):
            try:
                result = await effective_backend.execute(task)
                break
            except Exception as exc:
                if not _is_transient_llm_error(exc) or node_attempt == _NODE_LEVEL_MAX_RETRIES - 1:
                    raise
                last_exc = exc
                logger.warning(
                    "agent_node_retry",
                    stage=stage,
                    role=role,
                    attempt=node_attempt + 1,
                    max_retries=_NODE_LEVEL_MAX_RETRIES,
                    cooldown_s=_NODE_LEVEL_COOLDOWN_SECONDS,
                    error=str(exc)[:200],
                )
                await ctx.event_bus.emit(PipelineEvent(
                    cr_id=cr_id, event_type=EventType.AGENT_STARTED, stage=stage,
                    data={
                        "role": role, "repo": repo_name,
                        "retry": True,
                        "attempt": node_attempt + 1,
                        "reason": f"Transient LLM error, retrying in {_NODE_LEVEL_COOLDOWN_SECONDS}s",
                    },
                ))
                await asyncio.sleep(_NODE_LEVEL_COOLDOWN_SECONDS)

        set_span_attributes(s, {
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "cost_usd": result.cost_usd,
            "tool_calls_count": len(result.tool_calls),
            "round_count": result.round_count,
        })
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
