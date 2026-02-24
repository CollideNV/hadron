"""TDD Development node — test writer (red) + code writer (green) loop."""

from __future__ import annotations

from langgraph.types import RunnableConfig

import asyncio
import logging
from typing import Any

from hadron.agent.base import AgentTask
from hadron.agent.prompt import PromptComposer
from hadron.models.events import EventType, PipelineEvent
from hadron.models.pipeline_state import PipelineState

logger = logging.getLogger(__name__)


async def _run_tests(worktree_path: str, test_command: str) -> tuple[bool, str]:
    """Run the test suite and return (passed, output)."""
    proc = await asyncio.create_subprocess_shell(
        test_command,
        cwd=worktree_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
    output = stdout.decode(errors="replace")
    return proc.returncode == 0, output


async def tdd_node(state: PipelineState, config: RunnableConfig) -> dict[str, Any]:
    """TDD development: write tests (red) → implement code (green) → verify.

    Loops internally up to max_tdd_iterations if tests fail after implementation.
    """
    configurable = config.get("configurable", {})
    event_bus = configurable.get("event_bus")
    agent_backend = configurable.get("agent_backend")
    cr_id = state["cr_id"]
    pipeline_config = state.get("config_snapshot", {}).get("pipeline", {})
    max_iterations = pipeline_config.get("max_tdd_iterations", 5)

    if event_bus:
        await event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_ENTERED, stage="tdd"
        ))

    composer = PromptComposer()
    structured_cr = state.get("structured_cr", {})
    dev_results = []
    total_cost = 0.0
    total_input = 0
    total_output = 0

    for repo in state.get("affected_repos", []):
        repo_name = repo.get("repo_name", "")
        worktree_path = repo.get("worktree_path", "")
        test_command = repo.get("test_command", "pytest")
        language = repo.get("language", "python")

        repo_context = composer.build_repo_context(
            agents_md=repo.get("agents_md", ""),
            language=language,
            test_command=test_command,
        )

        cr_text = f"""# Change Request

**Title:** {structured_cr.get('title', '')}
**Description:** {structured_cr.get('description', '')}

**Acceptance Criteria:**
{chr(10).join(f'- {c}' for c in structured_cr.get('acceptance_criteria', []))}
"""

        # Include review feedback if this is a retry from review
        review_feedback = ""
        for rr in state.get("review_results", []):
            if rr.get("repo_name") == repo_name and rr.get("findings"):
                review_feedback = "## Review Findings to Address\n\n"
                for f in rr["findings"]:
                    review_feedback += f"- [{f.get('severity', '')}] {f.get('message', '')} ({f.get('file', '')}:{f.get('line', 0)})\n"

        # === RED PHASE: Write failing tests ===
        if event_bus:
            await event_bus.emit(PipelineEvent(
                cr_id=cr_id, event_type=EventType.AGENT_STARTED, stage="tdd",
                data={"role": "test_writer", "repo": repo_name},
            ))

        test_system = composer.compose_system_prompt("test_writer", repo_context)
        test_user = composer.compose_user_prompt(cr_text, review_feedback)

        test_task = AgentTask(
            role="test_writer",
            system_prompt=test_system,
            user_prompt=test_user,
            working_directory=worktree_path,
            model=configurable.get("model", "claude-sonnet-4-20250514"),
        )
        test_result = await agent_backend.execute(test_task)
        total_cost += test_result.cost_usd
        total_input += test_result.input_tokens
        total_output += test_result.output_tokens

        if event_bus:
            await event_bus.emit(PipelineEvent(
                cr_id=cr_id, event_type=EventType.AGENT_COMPLETED, stage="tdd",
                data={"role": "test_writer", "repo": repo_name},
            ))

        # === GREEN PHASE: Implement code (with retry loop) ===
        tests_passing = False
        test_output = ""
        iteration = 0

        for iteration in range(max_iterations):
            if event_bus:
                await event_bus.emit(PipelineEvent(
                    cr_id=cr_id, event_type=EventType.AGENT_STARTED, stage="tdd",
                    data={"role": "code_writer", "repo": repo_name, "iteration": iteration},
                ))

            code_system = composer.compose_system_prompt("code_writer", repo_context)

            code_payload = cr_text
            if iteration > 0 and test_output:
                code_payload += f"\n\n## Test Failure Output (iteration {iteration})\n\n```\n{test_output[-3000:]}\n```\n\nFix the implementation to make the failing tests pass."

            code_user = composer.compose_user_prompt(code_payload, review_feedback)

            code_task = AgentTask(
                role="code_writer",
                system_prompt=code_system,
                user_prompt=code_user,
                working_directory=worktree_path,
                model=configurable.get("model", "claude-sonnet-4-20250514"),
            )
            code_result = await agent_backend.execute(code_task)
            total_cost += code_result.cost_usd
            total_input += code_result.input_tokens
            total_output += code_result.output_tokens

            if event_bus:
                await event_bus.emit(PipelineEvent(
                    cr_id=cr_id, event_type=EventType.AGENT_COMPLETED, stage="tdd",
                    data={"role": "code_writer", "repo": repo_name, "iteration": iteration},
                ))

            # Run tests
            tests_passing, test_output = await _run_tests(worktree_path, test_command)

            if event_bus:
                await event_bus.emit(PipelineEvent(
                    cr_id=cr_id, event_type=EventType.TEST_RUN, stage="tdd",
                    data={
                        "repo": repo_name,
                        "passed": tests_passing,
                        "iteration": iteration,
                        "output_tail": test_output[-500:],
                    },
                ))

            if tests_passing:
                logger.info("Tests passing for %s after iteration %d", repo_name, iteration)
                break
            else:
                logger.info("Tests failing for %s at iteration %d, retrying...", repo_name, iteration)

        # Commit the work
        from hadron.git.worktree import WorktreeManager
        wm = WorktreeManager(configurable.get("workspace_dir", "/tmp/hadron-workspace"))
        await wm.commit_and_push(
            worktree_path,
            f"feat: TDD implementation for {cr_id} ({'green' if tests_passing else 'red'})",
        )

        dev_results.append({
            "repo_name": repo_name,
            "test_files": {},
            "code_files": {},
            "test_output": test_output[-2000:],
            "tests_passing": tests_passing,
            "dev_iteration": iteration + 1,
        })

    if event_bus:
        await event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_COMPLETED, stage="tdd",
            data={"all_passing": all(r["tests_passing"] for r in dev_results)},
        ))

    return {
        "dev_results": dev_results,
        "dev_loop_count": state.get("dev_loop_count", 0) + 1,
        "current_stage": "tdd",
        "cost_input_tokens": total_input,
        "cost_output_tokens": total_output,
        "cost_usd": total_cost,
        "stage_history": [{"stage": "tdd", "status": "completed"}],
    }
