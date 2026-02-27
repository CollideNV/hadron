"""Tests for the deterministic diff scope analyser."""

from __future__ import annotations

import pytest

from hadron.pipeline.diff_scope import (
    ScopeFlag,
    _extract_modified_files,
    analyse_diff_scope,
)


def _make_diff(*paths: str) -> str:
    """Build a minimal unified diff string touching the given file paths."""
    chunks = []
    for p in paths:
        chunks.append(
            f"diff --git a/{p} b/{p}\n"
            f"--- a/{p}\n"
            f"+++ b/{p}\n"
            f"@@ -1 +1 @@\n"
            f"-old\n"
            f"+new\n"
        )
    return "".join(chunks)


# ---------------------------------------------------------------------------
# _extract_modified_files
# ---------------------------------------------------------------------------


class TestExtractModifiedFiles:
    def test_single_file(self) -> None:
        assert _extract_modified_files(_make_diff("src/main.py")) == ["src/main.py"]

    def test_multiple_files(self) -> None:
        result = _extract_modified_files(_make_diff("a.py", "b.py", "c.py"))
        assert result == ["a.py", "b.py", "c.py"]

    def test_empty_diff(self) -> None:
        assert _extract_modified_files("") == []

    def test_no_headers(self) -> None:
        assert _extract_modified_files("just some random text\n") == []

    def test_renamed_file(self) -> None:
        diff = (
            "diff --git a/old_name.py b/new_name.py\n"
            "similarity index 95%\n"
            "rename from old_name.py\n"
            "rename to new_name.py\n"
        )
        # The regex extracts the b/ side
        assert _extract_modified_files(diff) == ["new_name.py"]


# ---------------------------------------------------------------------------
# Config pattern matching
# ---------------------------------------------------------------------------


class TestConfigPatterns:
    @pytest.mark.parametrize("path", [
        "Dockerfile",
        "services/api/Dockerfile",
        "docker-compose.yml",
        "infra/docker-compose.prod.yaml",
        ".github/workflows/ci.yml",
        ".gitlab-ci.yml",
        "ci/.gitlab-ci.yml",
        "Makefile",
        "infra/main.tf",
        ".env",
        ".env.production",
        "k8s/deployment.yaml",
        "deploy/staging.sh",
        "Jenkinsfile",
        "Procfile",
        "nginx.conf",
        "config/nginx.conf",
    ])
    def test_config_file_flagged(self, path: str) -> None:
        flags = analyse_diff_scope(_make_diff(path))
        config_flags = [f for f in flags if f.check == "config_scope"]
        assert len(config_flags) == 1, f"Expected config flag for {path}"
        assert config_flags[0].file == path

    @pytest.mark.parametrize("path", [
        "src/app.py",
        "README.md",
        "tests/test_main.py",
    ])
    def test_normal_file_not_flagged_as_config(self, path: str) -> None:
        flags = analyse_diff_scope(_make_diff(path))
        config_flags = [f for f in flags if f.check == "config_scope"]
        assert len(config_flags) == 0


# ---------------------------------------------------------------------------
# Dependency pattern matching
# ---------------------------------------------------------------------------


class TestDependencyPatterns:
    @pytest.mark.parametrize("path", [
        "package.json",
        "frontend/package.json",
        "package-lock.json",
        "requirements.txt",
        "requirements-dev.txt",
        "pyproject.toml",
        "backend/pyproject.toml",
        "Cargo.toml",
        "crates/core/Cargo.toml",
        "go.mod",
        "go.sum",
        "Gemfile",
        "Gemfile.lock",
        "pom.xml",
        "services/api/pom.xml",
        "build.gradle",
        "app/build.gradle.kts",
        "yarn.lock",
        "pnpm-lock.yaml",
        "composer.json",
        "libs/composer.json",
        "Pipfile",
        "Pipfile.lock",
    ])
    def test_dependency_file_flagged(self, path: str) -> None:
        flags = analyse_diff_scope(_make_diff(path))
        dep_flags = [f for f in flags if f.check == "dependency_scope"]
        assert len(dep_flags) == 1, f"Expected dependency flag for {path}"
        assert dep_flags[0].file == path

    @pytest.mark.parametrize("path", [
        "src/app.py",
        "README.md",
        "tests/test_main.py",
    ])
    def test_normal_file_not_flagged_as_dependency(self, path: str) -> None:
        flags = analyse_diff_scope(_make_diff(path))
        dep_flags = [f for f in flags if f.check == "dependency_scope"]
        assert len(dep_flags) == 0


# ---------------------------------------------------------------------------
# analyse_diff_scope — integration
# ---------------------------------------------------------------------------


class TestAnalyseDiffScope:
    def test_no_sensitive_files(self) -> None:
        assert analyse_diff_scope(_make_diff("src/main.py", "tests/test_main.py")) == []

    def test_config_only(self) -> None:
        flags = analyse_diff_scope(_make_diff("Dockerfile"))
        assert len(flags) == 1
        assert flags[0].check == "config_scope"

    def test_dependency_only(self) -> None:
        flags = analyse_diff_scope(_make_diff("package.json"))
        assert len(flags) == 1
        assert flags[0].check == "dependency_scope"

    def test_both_categories_from_different_files(self) -> None:
        flags = analyse_diff_scope(_make_diff("Dockerfile", "requirements.txt"))
        checks = {f.check for f in flags}
        assert checks == {"config_scope", "dependency_scope"}

    def test_mixed_sensitive_and_normal(self) -> None:
        flags = analyse_diff_scope(_make_diff("src/app.py", "Makefile", "go.mod"))
        assert len(flags) == 2
        checks = {f.check for f in flags}
        assert checks == {"config_scope", "dependency_scope"}

    def test_empty_diff(self) -> None:
        assert analyse_diff_scope("") == []

    def test_single_file_both_config_and_dependency(self) -> None:
        """A file like .env is config; package.json is dependency. A single file can only match one category per pattern set, but can match both."""
        # .env matches config but not dependency
        flags = analyse_diff_scope(_make_diff(".env"))
        assert len(flags) == 1
        assert flags[0].check == "config_scope"
