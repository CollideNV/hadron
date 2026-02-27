"""Deterministic diff scope analyser — Layer 4 of prompt injection defense (adr/security.md §12.6).

Parses unified diffs to detect changes to config files, dependency manifests,
and other sensitive paths. Produces warning flags injected into the Security
Reviewer prompt so the LLM pays extra attention to these areas.

Pure Python, no LLM calls.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Patterns matched against file paths extracted from `diff --git a/... b/...` lines.

_CONFIG_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(^|/)Dockerfile"),
    re.compile(r"(^|/)docker-compose"),
    re.compile(r"(^|/)\.github/"),
    re.compile(r"(^|/)\.gitlab-ci"),
    re.compile(r"(^|/)Makefile$"),
    re.compile(r"\.tf$"),
    re.compile(r"(^|/)\.env"),
    re.compile(r"(^|/)k8s/"),
    re.compile(r"(^|/)deploy/"),
    re.compile(r"(^|/)Jenkinsfile"),
    re.compile(r"(^|/)Procfile$"),
    re.compile(r"(^|/)nginx\.conf"),
]

_DEPENDENCY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(^|/)package\.json$"),
    re.compile(r"(^|/)package-lock\.json$"),
    re.compile(r"(^|/)requirements.*\.txt$"),
    re.compile(r"(^|/)pyproject\.toml$"),
    re.compile(r"(^|/)Cargo\.toml$"),
    re.compile(r"(^|/)go\.mod$"),
    re.compile(r"(^|/)go\.sum$"),
    re.compile(r"(^|/)Gemfile"),
    re.compile(r"(^|/)pom\.xml$"),
    re.compile(r"(^|/)build\.gradle"),
    re.compile(r"(^|/)yarn\.lock$"),
    re.compile(r"(^|/)pnpm-lock\.yaml$"),
    re.compile(r"(^|/)composer\.json$"),
    re.compile(r"(^|/)Pipfile"),
]

# Matches `diff --git a/path b/path` — we extract the b/ side.
_DIFF_HEADER_RE = re.compile(r"^diff --git a/.+ b/(.+)$", re.MULTILINE)


@dataclass(frozen=True)
class ScopeFlag:
    """A warning produced by the diff scope analyser."""

    check: str   # "config_scope" | "dependency_scope"
    file: str    # path that triggered the flag
    message: str


def _extract_modified_files(diff: str) -> list[str]:
    """Extract file paths from unified diff headers."""
    return _DIFF_HEADER_RE.findall(diff)


def analyse_diff_scope(diff: str) -> list[ScopeFlag]:
    """Analyse a unified diff for sensitive file modifications.

    Returns a list of ScopeFlag warnings. These are informational — they do
    not block the review, but are injected into the Security Reviewer prompt
    so it pays extra attention to these files.

    # TODO: Endpoint scope check (new route definitions) is language-dependent
    #       and requires AST-level analysis. Deferred to a future iteration.
    """
    files = _extract_modified_files(diff)
    flags: list[ScopeFlag] = []

    for path in files:
        for pattern in _CONFIG_PATTERNS:
            if pattern.search(path):
                flags.append(ScopeFlag(
                    check="config_scope",
                    file=path,
                    message=f"Configuration/infrastructure file modified: {path}",
                ))
                break  # one flag per file is enough

        for pattern in _DEPENDENCY_PATTERNS:
            if pattern.search(path):
                flags.append(ScopeFlag(
                    check="dependency_scope",
                    file=path,
                    message=f"Dependency manifest modified: {path}",
                ))
                break

    return flags
