"""Phase prompt builder — constructs system/user prompts for each agent phase."""

from __future__ import annotations

from hadron.agent.base import AgentTask


class PhasePromptBuilder:
    """Builds prompts for the explore → plan → act pipeline phases."""

    def build_explore_system(self, task: AgentTask) -> str:
        """Build the system prompt for the explore phase."""
        from hadron.agent.prompt import _load_template

        try:
            return _load_template("explorer")
        except FileNotFoundError:
            return (
                "You are a codebase explorer. Use list_directory and read_file "
                "to understand the project structure. Produce a structured summary. "
                "Do NOT write files or run commands."
            )

    def build_plan_system(self, task: AgentTask) -> str:
        """Build the system prompt for the plan phase."""
        from hadron.agent.prompt import _load_template

        try:
            planner_template = _load_template("planner")
        except FileNotFoundError:
            planner_template = (
                "You are an implementation planner. Analyse the exploration results "
                "and produce a concrete implementation plan."
            )
        # Include the original role system prompt as context for the planner
        return f"{planner_template}\n\n## Original Role Instructions\n\n{task.system_prompt}"

    def build_plan_user(self, task: AgentTask, exploration_summary: str) -> str:
        """Build the user prompt for the plan phase."""
        parts = []
        if exploration_summary:
            parts.append(f"## Exploration Summary\n\n{exploration_summary}")
        parts.append(f"## Original Task\n\n{task.user_prompt}")
        return "\n\n".join(parts)

    def build_act_user(
        self, task: AgentTask, exploration_summary: str, plan_text: str
    ) -> str:
        """Build the user prompt for the act phase.

        If no explore/plan phases ran, returns the original user prompt unchanged
        for backwards compatibility.
        """
        if not exploration_summary and not plan_text:
            return task.user_prompt

        parts = []
        if plan_text:
            parts.append(f"## Implementation Plan\n\n{plan_text}")
        if exploration_summary:
            parts.append(f"## Codebase Context (from exploration)\n\n{exploration_summary}")
        parts.append(f"## Original Task\n\n{task.user_prompt}")
        return "\n\n".join(parts)
