"""Tests for language and test command auto-detection."""

from __future__ import annotations

import json

import pytest

from hadron.git.detect import detect_languages_and_tests, _parse_agents_md


@pytest.fixture
def repo(tmp_path):
    """Create a temporary directory to simulate a repo."""
    return tmp_path


class TestMarkerDetection:
    """Detect languages from marker files."""

    def test_python_pyproject(self, repo) -> None:
        (repo / "pyproject.toml").write_text("[project]\nname = 'foo'\n")
        langs, tests = detect_languages_and_tests(str(repo))
        assert "python" in langs
        assert "pytest" in tests

    def test_python_setup_py(self, repo) -> None:
        (repo / "setup.py").write_text("from setuptools import setup\nsetup()")
        langs, tests = detect_languages_and_tests(str(repo))
        assert "python" in langs
        assert "pytest" in tests

    def test_javascript_package_json(self, repo) -> None:
        (repo / "package.json").write_text(json.dumps({
            "name": "foo",
            "scripts": {"test": "jest"},
        }))
        langs, tests = detect_languages_and_tests(str(repo))
        assert "javascript" in langs
        assert "npm test" in tests

    def test_typescript_detected(self, repo) -> None:
        (repo / "package.json").write_text(json.dumps({"name": "foo"}))
        (repo / "tsconfig.json").write_text("{}")
        langs, tests = detect_languages_and_tests(str(repo))
        assert "typescript" in langs
        assert "javascript" not in langs

    def test_rust_cargo(self, repo) -> None:
        (repo / "Cargo.toml").write_text("[package]\nname = 'foo'\n")
        langs, tests = detect_languages_and_tests(str(repo))
        assert "rust" in langs
        assert "cargo test" in tests

    def test_go_mod(self, repo) -> None:
        (repo / "go.mod").write_text("module example.com/foo\n")
        langs, tests = detect_languages_and_tests(str(repo))
        assert "go" in langs
        assert "go test ./..." in tests

    def test_java_pom(self, repo) -> None:
        (repo / "pom.xml").write_text("<project></project>")
        langs, tests = detect_languages_and_tests(str(repo))
        assert "java" in langs
        assert "mvn test" in tests

    def test_csharp_csproj(self, repo) -> None:
        (repo / "Foo.csproj").write_text("<Project></Project>")
        langs, tests = detect_languages_and_tests(str(repo))
        assert "csharp" in langs
        assert "dotnet test" in tests

    def test_ruby_gemfile(self, repo) -> None:
        (repo / "Gemfile").write_text("source 'https://rubygems.org'\n")
        langs, tests = detect_languages_and_tests(str(repo))
        assert "ruby" in langs
        assert "bundle exec rspec" in tests

    def test_empty_repo(self, repo) -> None:
        langs, tests = detect_languages_and_tests(str(repo))
        assert langs == []
        assert tests == []


class TestPolyglotDetection:
    """Repos with multiple languages."""

    def test_python_and_javascript(self, repo) -> None:
        (repo / "pyproject.toml").write_text("[project]\nname = 'foo'\n")
        (repo / "package.json").write_text(json.dumps({"name": "foo"}))
        langs, tests = detect_languages_and_tests(str(repo))
        assert "python" in langs
        assert "javascript" in langs
        assert len(langs) == 2
        assert "pytest" in tests
        assert "npm test" in tests

    def test_python_and_rust(self, repo) -> None:
        (repo / "pyproject.toml").write_text("[project]\n")
        (repo / "Cargo.toml").write_text("[package]\n")
        langs, tests = detect_languages_and_tests(str(repo))
        assert "python" in langs
        assert "rust" in langs

    def test_no_duplicate_languages(self, repo) -> None:
        """pyproject.toml and setup.py both indicate Python — should not duplicate."""
        (repo / "pyproject.toml").write_text("[project]\n")
        (repo / "setup.py").write_text("from setuptools import setup\n")
        langs, tests = detect_languages_and_tests(str(repo))
        assert langs.count("python") == 1
        assert tests.count("pytest") == 1


class TestAgentsMdOverride:
    """AGENTS.md / CLAUDE.md overrides."""

    def test_language_override(self, repo) -> None:
        (repo / "pyproject.toml").write_text("[project]\n")
        agents_md = "## Languages: python, typescript\n## Test commands: pytest, npm test\n"
        langs, tests = detect_languages_and_tests(str(repo), agents_md=agents_md)
        assert langs == ["python", "typescript"]
        assert tests == ["pytest", "npm test"]

    def test_bold_format(self) -> None:
        """Parse **Languages:** format."""
        content = "**Languages:** go, rust\n**Test commands:** go test ./..., cargo test\n"
        langs, tests = _parse_agents_md(content)
        assert langs == ["go", "rust"]
        assert tests == ["go test ./...", "cargo test"]

    def test_single_language(self) -> None:
        content = "## Language: python\n## Test command: pytest -x\n"
        langs, tests = _parse_agents_md(content)
        assert langs == ["python"]
        assert tests == ["pytest -x"]

    def test_empty_agents_md(self) -> None:
        langs, tests = _parse_agents_md("")
        assert langs == []
        assert tests == []

    def test_agents_md_without_overrides(self) -> None:
        content = "# My Project\n\nThis is a service that does things.\n"
        langs, tests = _parse_agents_md(content)
        assert langs == []
        assert tests == []

    def test_override_takes_precedence(self, repo) -> None:
        """AGENTS.md overrides auto-detection entirely when both lang and test specified."""
        (repo / "pyproject.toml").write_text("[project]\n")
        (repo / "Cargo.toml").write_text("[package]\n")
        agents_md = "## Languages: python\n## Test commands: make test\n"
        langs, tests = detect_languages_and_tests(str(repo), agents_md=agents_md)
        assert langs == ["python"]  # not ["python", "rust"]
        assert tests == ["make test"]  # not ["pytest", "cargo test"]
