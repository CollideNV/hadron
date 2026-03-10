"""Behaviour Translation + Verification nodes."""

from __future__ import annotations

from langgraph.types import RunnableConfig

import json
import logging
from typing import Any

from hadron.agent.prompt import PromptComposer
from hadron.models.events import EventType, PipelineEvent
from hadron.models.pipeline_state import PipelineState
from hadron.pipeline.nodes import NodeContext, gather_files, run_agent

logger = logging.getLogger(__name__)


async def behaviour_translation_node(state: PipelineState, config: RunnableConfig) -> dict[str, Any]:
    """Spec Writer agent writes Gherkin .feature files for each repo."""
    ctx = NodeContext.from_config(config)
    cr_id = state["cr_id"]

    if ctx.event_bus:
        await ctx.event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_ENTERED, stage="behaviour_translation"
        ))

    composer = PromptComposer()
    structured_cr = state.get("structured_cr", {})

    repo = state.get("repo", {})
    repo_name = repo.get("repo_name", "")
    worktree_path = repo.get("worktree_path", "")

    repo_context = composer.build_repo_context(
        agents_md=repo.get("agents_md", ""),
        languages=repo.get("languages", []),
        test_commands=repo.get("test_commands", []),
    )
    system_prompt = composer.compose_system_prompt("spec_writer", repo_context)

    # Include feedback from verification if this is a retry
    feedback = ""
    existing_specs = state.get("behaviour_specs", [])
    for spec in existing_specs:
        if spec.get("repo_name") == repo_name and spec.get("verification_feedback"):
            feedback = spec["verification_feedback"]

    task_payload = f"""# Change Request

**Title:** {structured_cr.get('title', '')}
**Description:** {structured_cr.get('description', '')}

**Acceptance Criteria:**
{chr(10).join(f'- {c}' for c in structured_cr.get('acceptance_criteria', []))}
"""
    user_prompt = composer.compose_user_prompt(task_payload, feedback)

    agent_run = await run_agent(
        ctx,
        role="spec_writer",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        cr_id=cr_id,
        stage="behaviour_translation",
        repo_name=repo_name,
        working_directory=worktree_path,
        allowed_tools=["read_file", "write_file", "list_directory"],
        explore_model="",  # No explore/plan — spec_writer only needs the CR
        plan_model="",
    )
    result = agent_run.result

    specs_list = [{
        "repo_name": repo_name,
        "feature_files": {},  # Agent writes directly to disk
        "verified": False,
        "verification_feedback": "",
        "verification_iteration": state.get("verification_loop_count", 0),
    }]

    if ctx.event_bus:
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


async def behaviour_verification_node(state: PipelineState, config: RunnableConfig) -> dict[str, Any]:
    """Verifier agent checks completeness and consistency of specs."""
    ctx = NodeContext.from_config(config)
    cr_id = state["cr_id"]

    if ctx.event_bus:
        await ctx.event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_ENTERED, stage="behaviour_verification"
        ))

    composer = PromptComposer()
    structured_cr = state.get("structured_cr", {})

    repo = state.get("repo", {})
    repo_name = repo.get("repo_name", "")
    worktree_path = repo.get("worktree_path", "")

    system_prompt = composer.compose_system_prompt("spec_verifier")

    # Gather feature files so the verifier doesn't need to explore
    feature_content = gather_files(worktree_path, "features/**/*.feature")

    task_payload = f"""# Change Request

**Title:** {structured_cr.get('title', '')}
**Description:** {structured_cr.get('description', '')}

**Acceptance Criteria:**
{chr(10).join(f'- {c}' for c in structured_cr.get('acceptance_criteria', []))}

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
        repo_name=repo_name,
        working_directory=worktree_path,
        allowed_tools=["read_file", "list_directory"],
        explore_model="",  # No explore/plan — CR + feature files are injected directly
        plan_model="",
    )
    result = agent_run.result

    # Parse verification result — try multiple extraction strategies
    verification = None
    text = result.output
    for extract in [
        lambda t: t.split("```json")[1].split("```")[0] if "```json" in t else None,
        lambda t: t.split("```")[1].split("```")[0] if "```" in t else None,
        lambda t: t[t.index("{"):t.rindex("}") + 1] if "{" in t else None,
        lambda t: t,
    ]:
        try:
            candidate = extract(text)
            if candidate:
                verification = json.loads(candidate.strip())
                break
        except (json.JSONDecodeError, IndexError, ValueError):
            continue

    if verification is None:
        logger.error("Could not parse verifier output for %s: %s", repo_name, text[:500])
        verification = {"verified": False, "feedback": f"Verifier output was not valid JSON: {text[:200]}", "missing_scenarios": [], "issues": ["Output parsing failed"]}

    verified = verification.get("verified", True)
    feedback = verification.get("feedback", "")
    missing = verification.get("missing_scenarios", [])
    issues = verification.get("issues", [])

    if not verified:
        logger.warning(
            "Verification FAILED for repo %s (iteration %d): feedback=%s, missing=%s, issues=%s",
            repo_name, state.get("verification_loop_count", 0) + 1,
            feedback, missing, issues,
        )
    else:
        logger.info("Verification PASSED for repo %s", repo_name)

    updated_specs = [{
        "repo_name": repo_name,
        "feature_files": {},
        "verified": verified,
        "verification_feedback": feedback,
        "verification_iteration": state.get("verification_loop_count", 0) + 1,
    }]

    if ctx.event_bus:
        await ctx.event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_COMPLETED,
            stage=f"behaviour_verification:{repo_name}",
            data={
                "repo": repo_name,
                "verified": verified,
                "feedback": feedback,
                "missing_scenarios": missing,
                "issues": issues,
                "iteration": state.get("verification_loop_count", 0) + 1,
            },
        ))

    if ctx.event_bus:
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
