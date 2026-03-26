"""Review payload builders — format task payloads for each reviewer role.

Extracted from review.py for modularity. Each builder assembles the diff,
CR summary, scope flags, and behaviour specs into a role-specific prompt.
"""

from __future__ import annotations

from typing import Any

from hadron.config.limits import MAX_DIFF_CHARS
from hadron.pipeline.diff_scope import ScopeFlag
from hadron.pipeline.nodes.cr_format import format_cr_section, format_cr_summary


# ---------------------------------------------------------------------------
# Shared formatting helpers
# ---------------------------------------------------------------------------


def format_diff_section(diff: str, default_branch: str) -> str:
    """Format the diff section shared by all reviewers."""
    return f"""## Code Diff (feature branch vs {default_branch})

```diff
{diff[:MAX_DIFF_CHARS]}
```
"""


def format_repo_specs(behaviour_specs: list[dict[str, Any]], repo_name: str) -> str:
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


def format_scope_section(scope_flags: list[ScopeFlag], preamble: str = "The following sensitive files were modified in this diff:") -> str:
    """Format scope flags into markdown — called once, shared by all reviewers."""
    if not scope_flags:
        return ""
    section = "\n## Diff Scope Flags (Deterministic Pre-Pass)\n\n"
    section += preamble + "\n\n"
    for flag in scope_flags:
        section += f"- **[{flag.check}]** {flag.message}\n"
    return section


# ---------------------------------------------------------------------------
# Per-reviewer payload builders (receive pre-built shared sections)
# ---------------------------------------------------------------------------


def build_security_payload(
    structured_cr: dict[str, Any],
    diff_section: str,
    scope_section: str,
    spec_text: str,
    behaviour_specs: list[dict[str, Any]],
    repo_name: str,
) -> str:
    """Build the task payload for the Security Reviewer (adr/architecture.md §5)."""
    # Security reviewer gets a stronger preamble for scope flags
    sec_scope = scope_section.replace(
        "The following sensitive files were modified in this diff:",
        "The following sensitive files were modified. Pay extra attention to these:",
    ) if scope_section else ""

    return (
        format_cr_section(structured_cr, untrusted=True)
        + sec_scope
        + "\n## Behaviour Specs\n\n"
        + (spec_text if spec_text else "_No behaviour specs available for this repo._")
        + "\n\n"
        + diff_section
    )


def build_quality_payload(
    structured_cr: dict[str, Any],
    diff_section: str,
    scope_section: str,
    spec_text: str,
    behaviour_specs: list[dict[str, Any]],
    repo_name: str,
) -> str:
    """Build the task payload for the Quality Reviewer."""
    return (
        format_cr_summary(structured_cr)
        + scope_section
        + "\n## Behaviour Specs\n\n"
        + (spec_text if spec_text else "_No behaviour specs available for this repo._")
        + "\n\n"
        + diff_section
    )


def build_spec_compliance_payload(
    structured_cr: dict[str, Any],
    diff_section: str,
    scope_section: str,
    spec_text: str,
    behaviour_specs: list[dict[str, Any]],
    repo_name: str,
) -> str:
    """Build the task payload for the Spec Compliance Reviewer."""
    other_text = ""
    for spec in behaviour_specs:
        if spec.get("repo_name") != repo_name:
            other_text += f"\n### Repo: {spec.get('repo_name', 'unknown')}\n"
            for fname in spec.get("feature_files", {}):
                other_text += f"- {fname}\n"

    return (
        format_cr_summary(structured_cr)
        + scope_section
        + "\n## Behaviour Specs (This Repo)\n\n"
        + (spec_text if spec_text else "_No behaviour specs available._")
        + "\n\n"
        + (f"## Specs From Other Affected Repos\n{other_text}\n" if other_text else "")
        + diff_section
        + "\n**Instructions:** Use the `read_file` tool to read `.feature` files from the worktree "
        + "if you need the full spec content beyond what is provided above.\n"
    )
