"""Auto-detect languages and test commands from repository marker files.

Detection order:
1. AGENTS.md / CLAUDE.md — if present and declares test commands or languages,
   those override auto-detection.
2. Marker file scanning — detects all languages present in the repo.

A polyglot repo (e.g. Python + JavaScript) will have multiple entries.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Marker file → (language, default test command)
_MARKERS: list[tuple[str, str, str]] = [
    ("pyproject.toml", "python", "pytest"),
    ("setup.py", "python", "pytest"),
    ("setup.cfg", "python", "pytest"),
    ("package.json", "javascript", "npm test"),
    ("Cargo.toml", "rust", "cargo test"),
    ("go.mod", "go", "go test ./..."),
    ("pom.xml", "java", "mvn test"),
    ("build.gradle", "java", "gradle test"),
    ("build.gradle.kts", "kotlin", "gradle test"),
    ("Gemfile", "ruby", "bundle exec rspec"),
    ("mix.exs", "elixir", "mix test"),
    ("composer.json", "php", "phpunit"),
    ("*.csproj", "csharp", "dotnet test"),
    ("*.fsproj", "fsharp", "dotnet test"),
    ("Makefile", None, None),  # detected but no default lang/test
]

# TypeScript detection: if package.json exists and has tsconfig or ts deps
_TS_INDICATORS = ("tsconfig.json", "tsconfig.base.json")


def detect_languages_and_tests(
    worktree_path: str,
    agents_md: str = "",
) -> tuple[list[str], list[str]]:
    """Detect languages and test commands from a repository.

    Args:
        worktree_path: Path to the repo worktree.
        agents_md: Contents of AGENTS.md / CLAUDE.md (if found).

    Returns:
        (languages, test_commands) — both may have multiple entries for
        polyglot repos.
    """
    base = Path(worktree_path)

    # --- Phase 1: Check AGENTS.md / CLAUDE.md for explicit overrides ---
    override_langs, override_tests = _parse_agents_md(agents_md)
    if override_langs or override_tests:
        logger.info(
            "Using AGENTS.md overrides: languages=%s, test_commands=%s",
            override_langs, override_tests,
        )
        # Fall through to marker detection for anything not overridden
        if override_langs and override_tests:
            return override_langs, override_tests

    # --- Phase 2: Scan marker files ---
    # Scan root AND one level of subdirectories to catch monorepo layouts
    # (e.g. pyproject.toml at root, frontend/package.json nested).
    detected_langs: list[str] = []
    detected_tests: list[str] = []
    seen_langs: set[str] = set()

    scan_dirs = [base]
    scan_dirs.extend(
        d for d in sorted(base.iterdir())
        if d.is_dir() and not d.name.startswith(".")
    )

    for scan_dir in scan_dirs:
        for marker, lang, test_cmd in _MARKERS:
            if marker.startswith("*"):
                # Glob pattern (e.g. *.csproj)
                matches = list(scan_dir.glob(marker))
                found = len(matches) > 0
            else:
                found = (scan_dir / marker).is_file()

            if not found or lang is None:
                continue

            # Special case: package.json → check for TypeScript
            if marker == "package.json":
                actual_lang = _detect_js_or_ts(scan_dir)
                if actual_lang not in seen_langs:
                    detected_langs.append(actual_lang)
                    seen_langs.add(actual_lang)
                # Check for custom test script in package.json
                pkg_test = _read_package_json_test(scan_dir)
                if pkg_test and test_cmd:
                    test_cmd = pkg_test
                    # Prefix with subdir path for nested packages
                    if scan_dir != base:
                        rel = scan_dir.relative_to(base)
                        test_cmd = f"cd {rel} && {test_cmd}"
            elif lang not in seen_langs:
                detected_langs.append(lang)
                seen_langs.add(lang)

            if test_cmd and test_cmd not in detected_tests:
                detected_tests.append(test_cmd)

    # Merge: AGENTS.md overrides take precedence
    final_langs = override_langs or detected_langs
    final_tests = override_tests or detected_tests

    if not final_langs:
        logger.warning("No languages detected in %s", worktree_path)
    if not final_tests:
        logger.warning("No test commands detected in %s", worktree_path)

    return final_langs, final_tests


def _detect_js_or_ts(base: Path) -> str:
    """Determine if a JS project is actually TypeScript."""
    for indicator in _TS_INDICATORS:
        if (base / indicator).is_file():
            return "typescript"
    return "javascript"


def _read_package_json_test(base: Path) -> str | None:
    """Read the test script from package.json if it exists."""
    pkg_path = base / "package.json"
    try:
        data = json.loads(pkg_path.read_text(errors="replace"))
        test_script = data.get("scripts", {}).get("test", "")
        if test_script and test_script != 'echo "Error: no test specified" && exit 1':
            return "npm test"
    except (json.JSONDecodeError, OSError):
        pass
    return None


def _parse_agents_md(content: str) -> tuple[list[str], list[str]]:
    """Extract language and test command overrides from AGENTS.md / CLAUDE.md.

    Looks for patterns like:
        ## Languages: python, typescript
        ## Test command: pytest tests/ -v
        ## Test commands: pytest, npm test
    """
    if not content:
        return [], []

    languages: list[str] = []
    test_commands: list[str] = []

    for line in content.splitlines():
        stripped = line.strip()

        # Strip markdown formatting for easier matching
        clean = stripped.replace("*", "").replace("#", "").strip()

        # Match "Language(s): ..." or "Test command(s): ..."
        lang_match = re.match(
            r"languages?\s*:\s*(.+)", clean, re.IGNORECASE,
        )
        if lang_match:
            raw = lang_match.group(1).strip()
            languages = [l.strip().lower() for l in raw.split(",") if l.strip()]

        test_match = re.match(
            r"test\s+commands?\s*:\s*(.+)", clean, re.IGNORECASE,
        )
        if test_match:
            raw = test_match.group(1).strip().rstrip("*")
            # Test commands may contain commas in args, so only split on
            # comma-space or newlines, not bare commas
            if ", " in raw:
                test_commands = [t.strip() for t in raw.split(", ") if t.strip()]
            else:
                test_commands = [raw] if raw else []

    return languages, test_commands
