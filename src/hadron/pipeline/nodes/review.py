"""Code Review node — 3 parallel reviewers + deterministic diff scope pre-pass.

Architecture: adr/architecture.md §3 (review stage), §5 (security model).

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

from hadron.agent.base import AgentResult, CostAccumulator, merge_model_breakdowns
from hadron.config.defaults import DEFAULT_MODEL
from hadron.models.events import EventType, PipelineEvent
from hadron.models.pipeline_state import PipelineState
from hadron.pipeline.diff_scope import analyse_diff_scope
from hadron.pipeline.nodes import (
    NodeContext, RepoInfo, emit_cost_update, pipeline_node,
    run_agent,
)
from hadron.pipeline.nodes.diff_capture import emit_stage_diff
from hadron.pipeline.nodes.review_exec import REVIEWER_REGISTRY, run_single_reviewer
from hadron.pipeline.nodes.review_payload import (
    format_diff_section,
    format_repo_specs,
    format_scope_section,
)

# Backwards-compatible aliases for private API
_REVIEWER_REGISTRY = REVIEWER_REGISTRY
_run_single_reviewer = run_single_reviewer
_format_diff_section = format_diff_section
_format_repo_specs = format_repo_specs
_format_scope_section = format_scope_section

logger = logging.getLogger(__name__)


@pipeline_node("review")
async def review_node(state: PipelineState, ctx: NodeContext, cr_id: str) -> dict[str, Any]:
    """Three parallel reviewers examine the diff for each repo."""
    structured_cr = state.get("structured_cr", {})
    behaviour_specs = state.get("behaviour_specs", [])
    costs = CostAccumulator()

    ri = RepoInfo.from_state(state)
    review_loop = state.get("review_loop_count", 0)

    # 1. Get diff
    diff = await ctx.worktree_manager.get_diff(ri.worktree_path, ri.default_branch)

    # 2. Deterministic diff scope analysis (no LLM)
    scope_flags = analyse_diff_scope(diff)

    # 2b. Pre-build shared sections ONCE (diff, scope flags, spec text)
    diff_section = format_diff_section(diff, ri.default_branch)
    scope_section = format_scope_section(scope_flags)

    # Use cached feature content from behaviour verification
    feature_content = state.get("feature_content") or ""
    if feature_content:
        # Inject into behaviour_specs so format_repo_specs can find it
        for spec in behaviour_specs:
            if spec.get("repo_name") == ri.repo_name and not spec.get("feature_files"):
                spec["feature_content_from_disk"] = feature_content

    spec_text = format_repo_specs(behaviour_specs, ri.repo_name)

    # Emit diff capturing what reviewers will evaluate
    await emit_stage_diff(
        ctx.event_bus, cr_id, "review", ri.repo_name,
        ctx.worktree_manager, ri.worktree_path, ri.default_branch,
        feature_content=feature_content,
    )

    # 3. Build payloads and run all reviewers in parallel
    payload_args = (structured_cr, diff_section, scope_section, spec_text, behaviour_specs, ri.repo_name)
    reviewer_tasks = []
    for role, build_payload in REVIEWER_REGISTRY.items():
        payload = build_payload(*payload_args)
        # Security reviewer runs on Sonnet (misses matter); others use Haiku.
        model = DEFAULT_MODEL if role == "security_reviewer" else None
        reviewer_tasks.append(
            run_single_reviewer(role, payload, ctx, cr_id, ri.repo_name, ri.worktree_path, review_loop, model=model)
        )
    reviewer_results = await asyncio.gather(*reviewer_tasks)

    # 5. Merge findings, summaries, and costs
    all_findings: list[dict[str, Any]] = []
    summaries: list[str] = []
    for role, r in zip(REVIEWER_REGISTRY, reviewer_results):
        await emit_cost_update(ctx.event_bus, cr_id, f"review:{role}", AgentResult(
            output="",
            cost_usd=r["cost_usd"],
            input_tokens=r["input_tokens"],
            output_tokens=r["output_tokens"],
        ), costs.total_cost)
        costs.total_cost += r["cost_usd"]
        costs.total_input += r["input_tokens"]
        costs.total_output += r["output_tokens"]
        costs.throttle_count += r.get("throttle_count", 0)
        costs.throttle_seconds += r.get("throttle_seconds", 0.0)
        costs.model_breakdown = merge_model_breakdowns(costs.model_breakdown, r.get("model_breakdown", {}))
        all_findings.extend(r["review"].get("findings", []))
        summary = r["review"].get("summary", "")
        if summary:
            summaries.append(f"**{role}**: {summary}")

    # 6. Emit individual findings
    for finding in all_findings:
        await ctx.event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.REVIEW_FINDING, stage="review",
            data={"repo": ri.repo_name, "review_round": review_loop, **finding},
        ))

    # 7. Determine pass/fail — only block on critical/major from ANY reviewer
    blocking_findings = [f for f in all_findings if f.get("severity") in ("critical", "major")]
    passed = len(blocking_findings) == 0

    review_results = [{
        "repo_name": ri.repo_name,
        "findings": all_findings,
        "review_passed": passed,
        "review_iteration": state.get("review_loop_count", 0) + 1,
        "summary": "\n".join(summaries),
    }]

    await ctx.event_bus.emit(PipelineEvent(
        cr_id=cr_id, event_type=EventType.STAGE_COMPLETED, stage="review",
        data={"all_passed": passed},
    ))

    return {
        "review_results": review_results,
        "review_passed": passed,
        "review_loop_count": state.get("review_loop_count", 0) + 1,
        "review_finding_counts": [len(blocking_findings)],
        "current_stage": "review",
        **costs.to_state_dict(),
        "stage_history": [{"stage": "review", "status": "completed"}],
    }
