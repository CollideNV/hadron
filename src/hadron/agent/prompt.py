"""Prompt composer — assembles the 4-layer prompt for each agent role."""

from __future__ import annotations

import functools
import logging
from pathlib import Path

from hadron.utils.text import truncate

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts" / "v1"
_MAX_STATIC_CONTEXT_CHARS = 48_000  # ~12k tokens


@functools.lru_cache(maxsize=None)
def _load_template_from_disk(role: str) -> str:
    """Load a prompt template by role name from disk (cached after first read)."""
    path = _PROMPTS_DIR / f"{role}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text()


class PromptComposer:
    """Assembles 4-layer prompts per adr/agents.md §11.

    Layer 1: Role system prompt (from templates)
    Layer 2: Repo context (AGENTS.md + directory tree)
    Layer 3: Task payload (CR, specs, code — from PipelineState)
    Layer 4: Loop feedback (previous review findings, test failures, etc.)
    """

    def __init__(self) -> None:
        self._cache: dict[str, str] = {}

    @classmethod
    def from_snapshot(cls, prompts: dict[str, str]) -> PromptComposer:
        """Create a PromptComposer pre-loaded from a config snapshot."""
        composer = cls()
        composer._cache = dict(prompts)
        return composer

    async def load_all(self, session_factory) -> None:  # noqa: ANN001
        """Bulk-load all prompt templates from the database into the cache."""
        from hadron.db.models import PromptTemplate
        from sqlalchemy import select

        async with session_factory() as session:
            result = await session.execute(select(PromptTemplate))
            for row in result.scalars():
                self._cache[row.role] = row.content

    def _get_template(self, role: str) -> str:
        """Get template from cache, falling back to disk."""
        if role in self._cache:
            return self._cache[role]
        return _load_template_from_disk(role)

    def compose_system_prompt(
        self,
        role: str,
        repo_context: str = "",
    ) -> str:
        """Build the system prompt (Layers 1 + 2)."""
        template = self._get_template(role)
        parts = [template]

        if repo_context:
            context = truncate(repo_context, _MAX_STATIC_CONTEXT_CHARS)
            parts.append(f"\n## Repository Context\n\n{context}")

        return "\n".join(parts)

    def compose_user_prompt(
        self,
        task_payload: str,
        feedback: str = "",
    ) -> str:
        """Build the user prompt (Layers 3 + 4)."""
        parts = [task_payload]

        if feedback:
            parts.append(f"\n## Previous Feedback\n\n{feedback}")

        return "\n".join(parts)

    def build_repo_context(
        self,
        agents_md: str = "",
        directory_tree: str = "",
        languages: list[str] | None = None,
        test_commands: list[str] | None = None,
    ) -> str:
        """Build Layer 2 repo context string."""
        parts = []
        if agents_md:
            parts.append(f"### AGENTS.md (authoritative — follow these instructions over assumptions)\n\n{agents_md}")
        if languages:
            parts.append(f"### Languages: {', '.join(languages)}")
        if test_commands:
            cmds = ", ".join(f"`{c}`" for c in test_commands)
            parts.append(f"### Test commands (use exactly as shown via run_command): {cmds}")
        if directory_tree:
            parts.append(f"### Directory Structure\n\n```\n{directory_tree}\n```")
        return "\n\n".join(parts)
