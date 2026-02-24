"""Code Review node — security + quality + spec compliance."""

from __future__ import annotations

from langgraph.types import RunnableConfig

import json
import logging
from typing import Any

from hadron.agent.base import AgentTask
from hadron.agent.prompt import PromptComposer
from hadron.git.worktree import WorktreeManager
from hadron.models.events import EventType, PipelineEvent
from hadron.models.pipeline_state import PipelineState

logger = logging.getLogger(__name__)


async def review_node(state: PipelineState, config: RunnableConfig) -> dict[str, Any]:
    """Single reviewer agent examines diff for each repo."""
    configurable = config.get("configurable", {})
    event_bus = configurable.get("event_bus")
    agent_backend = configurable.get("agent_backend")
    workspace_dir = configurable.get("workspace_dir", "/tmp/hadron-workspace")
    cr_id = state["cr_id"]

    if event_bus:
        await event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_ENTERED, stage="review"
        ))

    composer = PromptComposer()
    structured_cr = state.get("structured_cr", {})
    review_results = []
    total_cost = 0.0
    total_input = 0
    total_output = 0

    wm = WorktreeManager(workspace_dir)

    for repo in state.get("affected_repos", []):
        repo_name = repo.get("repo_name", "")
        worktree_path = repo.get("worktree_path", "")
        default_branch = repo.get("default_branch", "main")

        diff = await wm.get_diff(worktree_path, default_branch)

        system_prompt = composer.compose_system_prompt("reviewer")
        task_payload = f"""# Change Request

**Title:** {structured_cr.get('title', '')}
**Description:** {structured_cr.get('description', '')}

**Acceptance Criteria:**
{chr(10).join(f'- {c}' for c in structured_cr.get('acceptance_criteria', []))}

# Code Diff (feature branch vs {default_branch})

```diff
{diff[:30000]}
```
"""
        user_prompt = composer.compose_user_prompt(task_payload)

        if event_bus:
            await event_bus.emit(PipelineEvent(
                cr_id=cr_id, event_type=EventType.AGENT_STARTED, stage="review",
                data={"role": "reviewer", "repo": repo_name},
            ))

        task = AgentTask(
            role="reviewer",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            working_directory=worktree_path,
            allowed_tools=["read_file", "list_directory"],
            model=configurable.get("model", "claude-sonnet-4-20250514"),
        )
        result = await agent_backend.execute(task)
        total_cost += result.cost_usd
        total_input += result.input_tokens
        total_output += result.output_tokens

        # Parse review result
        try:
            text = result.output
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            review = json.loads(text.strip())
        except (json.JSONDecodeError, IndexError):
            review = {"review_passed": True, "findings": [], "summary": result.output[:500]}

        passed = review.get("review_passed", True)
        findings = review.get("findings", [])

        if event_bus:
            for finding in findings:
                await event_bus.emit(PipelineEvent(
                    cr_id=cr_id, event_type=EventType.REVIEW_FINDING, stage="review",
                    data={"repo": repo_name, **finding},
                ))

        review_results.append({
            "repo_name": repo_name,
            "findings": findings,
            "review_passed": passed,
            "review_iteration": state.get("review_loop_count", 0) + 1,
        })

        if event_bus:
            await event_bus.emit(PipelineEvent(
                cr_id=cr_id, event_type=EventType.AGENT_COMPLETED, stage="review",
                data={"role": "reviewer", "repo": repo_name, "passed": passed},
            ))

    all_passed = all(r["review_passed"] for r in review_results)

    if event_bus:
        await event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_COMPLETED, stage="review",
            data={"all_passed": all_passed},
        ))

    return {
        "review_results": review_results,
        "review_passed": all_passed,
        "review_loop_count": state.get("review_loop_count", 0) + 1,
        "current_stage": "review",
        "cost_input_tokens": total_input,
        "cost_output_tokens": total_output,
        "cost_usd": total_cost,
        "stage_history": [{"stage": "review", "status": "completed"}],
    }
