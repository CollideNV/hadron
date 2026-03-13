"""Intake node — parse raw CR into structured CR using LLM."""

from __future__ import annotations

import logging
from typing import Any

from hadron.config.defaults import DEFAULT_EXPLORE_MODEL
from hadron.models.events import EventType, PipelineEvent
from hadron.models.pipeline_state import PipelineState
from hadron.pipeline.nodes import NodeContext, extract_json, pipeline_node, run_agent
from hadron.pipeline.nodes.cr_format import format_cr_section

logger = logging.getLogger(__name__)


@pipeline_node("intake")
async def intake_node(state: PipelineState, ctx: NodeContext, cr_id: str) -> dict[str, Any]:
    """Parse raw CR text into a structured change request."""
    system_prompt = ctx.prompt_composer.compose_system_prompt("intake_parser")
    user_prompt = format_cr_section({
        "title": state.get("raw_cr_title", ""),
        "description": state.get("raw_cr_text", ""),
    })

    agent_run = await run_agent(
        ctx,
        role="intake_parser",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        cr_id=cr_id,
        stage="intake",
        allowed_tools=[],
        model=DEFAULT_EXPLORE_MODEL,  # Simple JSON extraction — Haiku suffices
        explore_model="",
        plan_model="",
    )
    result = agent_run.result

    # Parse JSON from agent output
    structured = extract_json(result.output, context="intake")
    if structured is None:
        # Per design principle: "pipeline never silently fails".
        # Return a paused status so the human gets a decision screen
        # instead of proceeding with degraded data.
        return {
            "structured_cr": {
                "title": state.get("raw_cr_title", ""),
                "description": state.get("raw_cr_text", ""),
                "acceptance_criteria": [],
                "affected_domains": [],
                "priority": "medium",
                "constraints": [],
                "risk_flags": ["intake_parse_failed"],
            },
            "current_stage": "intake",
            "status": "paused",
            "error": "Intake agent output was not valid JSON — human review required",
            "cost_input_tokens": result.input_tokens,
            "cost_output_tokens": result.output_tokens,
            "cost_usd": result.cost_usd,
            "throttle_count": result.throttle_count,
            "throttle_seconds": result.throttle_seconds,
            "model_breakdown": result.model_breakdown,
            "stage_history": [{"stage": "intake", "status": "paused"}],
        }

    await ctx.event_bus.emit(PipelineEvent(
        cr_id=cr_id, event_type=EventType.STAGE_COMPLETED, stage="intake",
        data={"structured_cr": structured},
    ))

    return {
        "structured_cr": structured,
        "current_stage": "intake",
        "cost_input_tokens": result.input_tokens,
        "cost_output_tokens": result.output_tokens,
        "cost_usd": result.cost_usd,
        "throttle_count": result.throttle_count,
        "throttle_seconds": result.throttle_seconds,
        "model_breakdown": result.model_breakdown,
        "stage_history": [{"stage": "intake", "status": "completed"}],
    }
