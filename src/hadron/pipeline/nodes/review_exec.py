"""Review execution — run individual reviewer agents and collect results.

Extracted from review.py for modularity. Contains the reviewer registry
and the single-reviewer execution function.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from hadron.agent.prompt import PromptComposer
from hadron.config.defaults import DEFAULT_EXPLORE_MODEL
from hadron.models.events import EventType, PipelineEvent
from hadron.pipeline.nodes import NodeContext, extract_json, run_agent
from hadron.pipeline.nodes.review_payload import (
    build_quality_payload,
    build_security_payload,
    build_spec_compliance_payload,
)

logger = logging.getLogger(__name__)


REVIEWER_REGISTRY: dict[str, Callable[..., str]] = {
    "security_reviewer": build_security_payload,
    "quality_reviewer": build_quality_payload,
    "spec_compliance_reviewer": build_spec_compliance_payload,
}


async def run_single_reviewer(
    role: str,
    task_payload: str,
    ctx: NodeContext,
    cr_id: str,
    repo_name: str,
    worktree_path: str,
    loop_iteration: int = 0,
    model: str | None = None,
) -> dict[str, Any]:
    """Run a single reviewer agent and return parsed results + cost info."""
    sub_stage = f"review:{role}"

    composer = PromptComposer()
    system_prompt = composer.compose_system_prompt(role)
    user_prompt = composer.compose_user_prompt(task_payload)

    await ctx.event_bus.emit(PipelineEvent(
        cr_id=cr_id, event_type=EventType.STAGE_ENTERED, stage=sub_stage,
    ))

    agent_run = await run_agent(
        ctx,
        role=role,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        cr_id=cr_id,
        stage=sub_stage,
        repo_name=repo_name,
        working_directory=worktree_path,
        allowed_tools=["read_file", "list_directory"],
        model=model or DEFAULT_EXPLORE_MODEL,
        explore_model="",
        plan_model="",
        loop_iteration=loop_iteration,
    )
    result = agent_run.result

    # Parse JSON from agent output
    review = extract_json(result.output, context=f"review:{role}")
    if review is None:
        # SAFETY: If we can't parse the reviewer's output, assume the review FAILED.
        review = {"review_passed": False, "findings": [{"severity": "major", "reviewer": role, "message": "Could not parse reviewer output as JSON — treating as failed review"}], "summary": result.output[:500]}

    # Tag findings with reviewer name if not already present
    for finding in review.get("findings", []):
        finding.setdefault("reviewer", role)

    await ctx.event_bus.emit(PipelineEvent(
        cr_id=cr_id, event_type=EventType.STAGE_COMPLETED, stage=sub_stage,
    ))

    return {
        "review": review,
        "cost_usd": result.cost_usd,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "throttle_count": result.throttle_count,
        "throttle_seconds": result.throttle_seconds,
        "model_breakdown": result.model_breakdown,
    }
