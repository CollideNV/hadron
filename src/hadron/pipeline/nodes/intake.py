"""Intake node — parse raw CR into structured CR using LLM."""

from __future__ import annotations

from langgraph.types import RunnableConfig

import json
import logging
from typing import Any

from hadron.agent.prompt import PromptComposer
from hadron.models.events import EventType, PipelineEvent
from hadron.models.pipeline_state import PipelineState
from hadron.pipeline.nodes import NodeContext, run_agent

logger = logging.getLogger(__name__)


async def intake_node(state: PipelineState, config: RunnableConfig) -> dict[str, Any]:
    """Parse raw CR text into a structured change request."""
    ctx = NodeContext.from_config(config)
    cr_id = state["cr_id"]

    if ctx.event_bus:
        await ctx.event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_ENTERED, stage="intake"
        ))

    composer = PromptComposer()
    system_prompt = composer.compose_system_prompt("intake_parser")
    user_prompt = f"# Change Request\n\n**Title:** {state.get('raw_cr_title', '')}\n\n**Description:**\n{state.get('raw_cr_text', '')}"

    agent_run = await run_agent(
        ctx,
        role="intake_parser",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        cr_id=cr_id,
        stage="intake",
        allowed_tools=[],
        explore_model="",  # No explore/plan for intake
        plan_model="",
    )
    result = agent_run.result

    # Parse JSON from agent output
    try:
        text = result.output
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        structured = json.loads(text.strip())
    except (json.JSONDecodeError, IndexError):
        logger.error("Failed to parse intake output as JSON: %s", result.output[:200])
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
            "stage_history": [{"stage": "intake", "status": "paused"}],
        }

    if ctx.event_bus:
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
        "stage_history": [{"stage": "intake", "status": "completed"}],
    }
