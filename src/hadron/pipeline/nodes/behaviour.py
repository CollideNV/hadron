"""Behaviour Translation + Verification nodes."""

from __future__ import annotations

import logging
from typing import Any

from hadron.agent.prompt import PromptComposer
from hadron.config.defaults import DEFAULT_EXPLORE_MODEL
from hadron.models.events import EventType, PipelineEvent
from hadron.models.pipeline_state import PipelineState
from hadron.pipeline.nodes import (
    NodeContext, RepoInfo, extract_json, gather_files, pipeline_node, run_agent,
)
from hadron.pipeline.nodes.cr_format import format_cr_section

logger = logging.getLogger(__name__)


@pipeline_node("behaviour_translation")
async def behaviour_translation_node(state: PipelineState, ctx: NodeContext, cr_id: str) -> dict[str, Any]:
    """Spec Writer agent writes Gherkin .feature files for each repo."""
    composer = PromptComposer()
    structured_cr = state.get("structured_cr", {})
    ri = RepoInfo.from_state(state)

    repo_context = composer.build_repo_context(
        agents_md=ri.agents_md,
        languages=ri.languages,
        test_commands=ri.test_commands,
    )
    system_prompt = composer.compose_system_prompt("spec_writer", repo_context)

    # Include feedback from verification if this is a retry
    feedback = ""
    existing_specs = state.get("behaviour_specs", [])
    for spec in existing_specs:
        if spec.get("repo_name") == ri.repo_name and spec.get("verification_feedback"):
            feedback = spec["verification_feedback"]

    task_payload = format_cr_section(structured_cr)
    user_prompt = composer.compose_user_prompt(task_payload, feedback)

    agent_run = await run_agent(
        ctx,
        role="spec_writer",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        cr_id=cr_id,
        stage="behaviour_translation",
        repo_name=ri.repo_name,
        working_directory=ri.worktree_path,
        allowed_tools=["read_file", "write_file", "list_directory"],
        explore_model="",  # No explore — spec_writer works from CR, not code
        plan_model="",
    )
    result = agent_run.result

    specs_list = [{
        "repo_name": ri.repo_name,
        "feature_files": {},  # Agent writes directly to disk
        "verified": False,
        "verification_feedback": "",
        "verification_iteration": state.get("verification_loop_count", 0),
    }]

    await ctx.event_bus.emit(PipelineEvent(
        cr_id=cr_id, event_type=EventType.STAGE_COMPLETED, stage="behaviour_translation",
    ))

    return {
        "behaviour_specs": specs_list,
        "current_stage": "behaviour_translation",
        "cost_input_tokens": result.input_tokens,
        "cost_output_tokens": result.output_tokens,
        "cost_usd": result.cost_usd,
        "stage_history": [{"stage": "behaviour_translation", "status": "completed"}],
    }


@pipeline_node("behaviour_verification")
async def behaviour_verification_node(state: PipelineState, ctx: NodeContext, cr_id: str) -> dict[str, Any]:
    """Verifier agent checks completeness and consistency of specs."""
    composer = PromptComposer()
    structured_cr = state.get("structured_cr", {})

    ri = RepoInfo.from_state(state)

    system_prompt = composer.compose_system_prompt("spec_verifier")

    # Gather feature files so the verifier doesn't need to explore
    feature_content = gather_files(ri.worktree_path, "features/**/*.feature")

    task_payload = format_cr_section(structured_cr) + f"""
## Feature Specifications

{feature_content if feature_content else "(No .feature files found)"}

Verify the above specifications against the CR.
"""
    user_prompt = composer.compose_user_prompt(task_payload)

    agent_run = await run_agent(
        ctx,
        role="spec_verifier",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        cr_id=cr_id,
        stage="behaviour_verification",
        repo_name=ri.repo_name,
        working_directory=ri.worktree_path,
        allowed_tools=["read_file", "list_directory"],
        model=DEFAULT_EXPLORE_MODEL,  # Structured comparison — Haiku suffices
        explore_model="",
        plan_model="",
    )
    result = agent_run.result

    # Parse verification result — try multiple extraction strategies
    verification = extract_json(result.output, context=f"spec_verifier:{ri.repo_name}")
    if verification is None:
        verification = {"verified": False, "feedback": f"Verifier output was not valid JSON: {result.output[:200]}", "missing_scenarios": [], "issues": ["Output parsing failed"]}

    verified = verification.get("verified", True)
    feedback = verification.get("feedback", "")
    missing = verification.get("missing_scenarios", [])
    issues = verification.get("issues", [])

    if not verified:
        logger.warning(
            "Verification FAILED for repo %s (iteration %d): feedback=%s, missing=%s, issues=%s",
            ri.repo_name, state.get("verification_loop_count", 0) + 1,
            feedback, missing, issues,
        )
    else:
        logger.info("Verification PASSED for repo %s", ri.repo_name)

    updated_specs = [{
        "repo_name": ri.repo_name,
        "feature_files": {},
        "verified": verified,
        "verification_feedback": feedback,
        "verification_iteration": state.get("verification_loop_count", 0) + 1,
    }]

    await ctx.event_bus.emit(PipelineEvent(
        cr_id=cr_id, event_type=EventType.STAGE_COMPLETED,
        stage=f"behaviour_verification:{ri.repo_name}",
        data={
            "repo": ri.repo_name,
            "verified": verified,
            "feedback": feedback,
            "missing_scenarios": missing,
            "issues": issues,
            "iteration": state.get("verification_loop_count", 0) + 1,
        },
    ))

    await ctx.event_bus.emit(PipelineEvent(
        cr_id=cr_id, event_type=EventType.STAGE_COMPLETED, stage="behaviour_verification",
        data={
            "all_verified": verified,
            "iteration": state.get("verification_loop_count", 0) + 1,
        },
    ))

    return {
        "behaviour_specs": updated_specs,
        "behaviour_verified": verified,
        "verification_loop_count": state.get("verification_loop_count", 0) + 1,
        "current_stage": "behaviour_verification",
        "cost_input_tokens": result.input_tokens,
        "cost_output_tokens": result.output_tokens,
        "cost_usd": result.cost_usd,
        "stage_history": [{"stage": "behaviour_verification", "status": "completed"}],
    }
