"""Unified agent execution with events, cost tracking, and conversation storage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hadron.agent.base import AgentCallbacks, AgentResult, AgentTask, OnAgentEvent, OnToolCall, PhaseConfig
from hadron.events.bus import EventBus
from hadron.models.events import EventType, PipelineEvent
from hadron.pipeline.nodes.callbacks import (
    emit_cost_update,
    make_agent_event_emitter,
    make_nudge_poller,
    make_tool_call_emitter,
    store_conversation,
)
from hadron.pipeline.nodes.context import NodeContext


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
