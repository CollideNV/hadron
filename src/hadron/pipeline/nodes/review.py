"""Code Review node — 3 parallel reviewers + deterministic diff scope pre-pass.

Architecture: adr/stages.md §8.7, adr/security.md §12.5, §12.6.

Flow:
  1. Get diff from worktree
  2. analyse_diff_scope(diff) → scope_flags (deterministic, no LLM)
  3. asyncio.gather(security_reviewer, quality_reviewer, spec_compliance_reviewer)
  4. Merge findings, emit events
  5. review_passed = no critical/major findings from ANY reviewer
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from hadron.agent.base import AgentResult, merge_model_breakdowns
from hadron.agent.prompt import PromptComposer
from hadron.config.defaults import DEFAULT_EXPLORE_MODEL
from hadron.config.limits import MAX_DIFF_CHARS
from hadron.models.events import EventType, PipelineEvent
from hadron.models.pipeline_state import PipelineState
from hadron.pipeline.diff_scope import ScopeFlag, analyse_diff_scope
from hadron.pipeline.nodes import (
    NodeContext, RepoInfo, emit_cost_update, extract_json, gather_changed_files, pipeline_node, run_agent,
)
from hadron.pipeline.nodes.cr_format import format_cr_section

logger = logging.getLogger(__name__)

# The three reviewer roles and their prompt template names.
_REVIEWER_ROLES = ("security_reviewer", "quality_reviewer", "spec_compliance_reviewer")


# ---------------------------------------------------------------------------
# Shared payload helpers
# ---------------------------------------------------------------------------


def _format_diff_section(diff: str, default_branch: str) -> str:
    """Format the diff section shared by all reviewers."""
    return f"""## Code Diff (feature branch vs {default_branch})

```diff
{diff[:MAX_DIFF_CHARS]}
```
"""


def _format_repo_specs(behaviour_specs: list[dict[str, Any]], repo_name: str) -> str:
    """Format Gherkin spec content for a specific repo."""
    for spec in behaviour_specs:
        if spec.get("repo_name") == repo_name:
            # Prefer content gathered from disk (spec writer writes to disk, not state)
            if spec.get("feature_content_from_disk"):
                return spec["feature_content_from_disk"]
            # Fallback to feature_files dict (if populated)
            text = ""
            for fname, content in spec.get("feature_files", {}).items():
                text += f"\n### {fname}\n```gherkin\n{content}\n```\n"
            if text:
                return text
    return ""


# ---------------------------------------------------------------------------
# Per-reviewer payload builders
# ---------------------------------------------------------------------------


def _build_security_payload(
    diff: str,
    structured_cr: dict[str, Any],
    default_branch: str,
    scope_flags: list[ScopeFlag],
    behaviour_specs: list[dict[str, Any]],
    repo_name: str,
) -> str:
    """Build the task payload for the Security Reviewer (adr/security.md §12.5)."""
    scope_section = ""
    if scope_flags:
        scope_section = "\n## Diff Scope Flags (Deterministic Pre-Pass)\n\n"
        scope_section += "The following sensitive files were modified. Pay extra attention to these:\n\n"
        for flag in scope_flags:
            scope_section += f"- **[{flag.check}]** {flag.message}\n"

    spec_text = _format_repo_specs(behaviour_specs, repo_name)

    return (
        format_cr_section(structured_cr, untrusted=True)
        + scope_section
        + "\n## Behaviour Specs\n\n"
        + (spec_text if spec_text else "_No behaviour specs available for this repo._")
        + "\n\n"
        + _format_diff_section(diff, default_branch)
    )


def _build_quality_payload(
    diff: str,
    structured_cr: dict[str, Any],
    default_branch: str,
    behaviour_specs: list[dict[str, Any]],
    repo_name: str,
) -> str:
    """Build the task payload for the Quality Reviewer."""
    spec_text = _format_repo_specs(behaviour_specs, repo_name)
    return (
        format_cr_section(structured_cr)
        + "\n## Behaviour Specs\n\n"
        + (spec_text if spec_text else "_No behaviour specs available for this repo._")
        + "\n\n"
        + _format_diff_section(diff, default_branch)
    )


def _build_spec_compliance_payload(
    diff: str,
    structured_cr: dict[str, Any],
    default_branch: str,
    behaviour_specs: list[dict[str, Any]],
    repo_name: str,
) -> str:
    """Build the task payload for the Spec Compliance Reviewer."""
    this_repo_text = _format_repo_specs(behaviour_specs, repo_name)

    other_text = ""
    for spec in behaviour_specs:
        if spec.get("repo_name") != repo_name:
            other_text += f"\n### Repo: {spec.get('repo_name', 'unknown')}\n"
            for fname in spec.get("feature_files", {}):
                other_text += f"- {fname}\n"

    return (
        format_cr_section(structured_cr)
        + "\n## Behaviour Specs (This Repo)\n\n"
        + (this_repo_text if this_repo_text else "_No behaviour specs available._")
        + "\n\n"
        + (f"## Specs From Other Affected Repos\n{other_text}\n" if other_text else "")
        + _format_diff_section(diff, default_branch)
        + "\n**Instructions:** Use the `read_file` tool to read `.feature` files from the worktree "
        + "if you need the full spec content beyond what is provided above.\n"
    )


async def _run_single_reviewer(
    role: str,
    task_payload: str,
    ctx: NodeContext,
    cr_id: str,
    repo_name: str,
    worktree_path: str,
    loop_iteration: int = 0,
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
        model=DEFAULT_EXPLORE_MODEL,  # Diff analysis + JSON output — Haiku suffices
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


@pipeline_node("review")
async def review_node(state: PipelineState, ctx: NodeContext, cr_id: str) -> dict[str, Any]:
    """Three parallel reviewers examine the diff for each repo."""
    structured_cr = state.get("structured_cr", {})
    behaviour_specs = state.get("behaviour_specs", [])
    total_cost = 0.0
    total_input = 0
    total_output = 0
    total_throttle_count = 0
    total_throttle_seconds = 0.0
    total_model_breakdown: dict[str, dict[str, Any]] = {}

    ri = RepoInfo.from_state(state)
    review_loop = state.get("review_loop_count", 0)

    # 1. Get diff
    diff = await ctx.worktree_manager.get_diff(ri.worktree_path, ri.default_branch)

    # 2. Deterministic diff scope analysis (no LLM)
    scope_flags = analyse_diff_scope(diff)

    # 2b. Gather feature files from disk (behaviour_specs[].feature_files is always
    # empty because the spec writer writes to disk, not to state)
    feature_content = gather_changed_files(ri.worktree_path, "features/**/*.feature", ri.default_branch)
    if feature_content:
        # Inject into behaviour_specs so payload builders can use _format_repo_specs
        for spec in behaviour_specs:
            if spec.get("repo_name") == ri.repo_name and not spec.get("feature_files"):
                spec["feature_content_from_disk"] = feature_content

    # 3. Build payloads for each reviewer
    security_payload = _build_security_payload(
        diff, structured_cr, ri.default_branch, scope_flags, behaviour_specs, ri.repo_name,
    )
    quality_payload = _build_quality_payload(diff, structured_cr, ri.default_branch, behaviour_specs, ri.repo_name)
    spec_payload = _build_spec_compliance_payload(
        diff, structured_cr, ri.default_branch, behaviour_specs, ri.repo_name,
    )

    # 4. Run all 3 reviewers in parallel
    security_result, quality_result, spec_result = await asyncio.gather(
        _run_single_reviewer("security_reviewer", security_payload, ctx, cr_id, ri.repo_name, ri.worktree_path, review_loop),
        _run_single_reviewer("quality_reviewer", quality_payload, ctx, cr_id, ri.repo_name, ri.worktree_path, review_loop),
        _run_single_reviewer("spec_compliance_reviewer", spec_payload, ctx, cr_id, ri.repo_name, ri.worktree_path, review_loop),
    )

    # 5. Merge findings and costs
    all_findings: list[dict[str, Any]] = []
    for role, r in zip(_REVIEWER_ROLES, (security_result, quality_result, spec_result)):
        await emit_cost_update(ctx.event_bus, cr_id, f"review:{role}", AgentResult(
            output="",
            cost_usd=r["cost_usd"],
            input_tokens=r["input_tokens"],
            output_tokens=r["output_tokens"],
        ), total_cost)
        total_cost += r["cost_usd"]
        total_input += r["input_tokens"]
        total_output += r["output_tokens"]
        total_throttle_count += r.get("throttle_count", 0)
        total_throttle_seconds += r.get("throttle_seconds", 0.0)
        total_model_breakdown = merge_model_breakdowns(total_model_breakdown, r.get("model_breakdown", {}))
        all_findings.extend(r["review"].get("findings", []))

    # 6. Emit individual findings
    for finding in all_findings:
        await ctx.event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.REVIEW_FINDING, stage="review",
            data={"repo": ri.repo_name, **finding},
        ))

    # 7. Determine pass/fail — only block on critical/major from ANY reviewer
    blocking_findings = [f for f in all_findings if f.get("severity") in ("critical", "major")]
    passed = len(blocking_findings) == 0

    review_results = [{
        "repo_name": ri.repo_name,
        "findings": all_findings,
        "review_passed": passed,
        "review_iteration": state.get("review_loop_count", 0) + 1,
    }]

    await ctx.event_bus.emit(PipelineEvent(
        cr_id=cr_id, event_type=EventType.STAGE_COMPLETED, stage="review",
        data={"all_passed": passed},
    ))

    return {
        "review_results": review_results,
        "review_passed": passed,
        "review_loop_count": state.get("review_loop_count", 0) + 1,
        "current_stage": "review",
        "cost_input_tokens": total_input,
        "cost_output_tokens": total_output,
        "cost_usd": total_cost,
        "throttle_count": total_throttle_count,
        "throttle_seconds": total_throttle_seconds,
        "model_breakdown": total_model_breakdown,
        "stage_history": [{"stage": "review", "status": "completed"}],
    }
