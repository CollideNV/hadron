"""Tests for language and test command auto-detection."""

from __future__ import annotations

import json

import pytest

from hadron.git.detect import detect_e2e_tests, detect_languages_and_tests, _parse_agents_md


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
        langs, tests, e2e = _parse_agents_md(content)
        assert langs == ["go", "rust"]
        assert tests == ["go test ./...", "cargo test"]
        assert e2e is None

    def test_single_language(self) -> None:
        content = "## Language: python\n## Test command: pytest -x\n"
        langs, tests, _ = _parse_agents_md(content)
        assert langs == ["python"]
        assert tests == ["pytest -x"]

    def test_empty_agents_md(self) -> None:
        langs, tests, e2e = _parse_agents_md("")
        assert langs == []
        assert tests == []
        assert e2e is None

    def test_agents_md_without_overrides(self) -> None:
        content = "# My Project\n\nThis is a service that does things.\n"
        langs, tests, e2e = _parse_agents_md(content)
        assert langs == []
        assert tests == []
        assert e2e is None

    def test_e2e_test_command_override(self) -> None:
        content = "## E2E test command: npx playwright test\n"
        _, _, e2e = _parse_agents_md(content)
        assert e2e == ["npx playwright test"]

    def test_e2e_tests_none(self) -> None:
        content = "## E2E tests: none\n"
        _, _, e2e = _parse_agents_md(content)
        assert e2e == []

    def test_e2e_multiple_commands(self) -> None:
        content = "## E2E test commands: npx playwright test, npx cypress run\n"
        _, _, e2e = _parse_agents_md(content)
        assert e2e == ["npx playwright test", "npx cypress run"]

    def test_override_takes_precedence(self, repo) -> None:
        """AGENTS.md overrides auto-detection entirely when both lang and test specified."""
        (repo / "pyproject.toml").write_text("[project]\n")
        (repo / "Cargo.toml").write_text("[package]\n")
        agents_md = "## Languages: python\n## Test commands: make test\n"
        langs, tests = detect_languages_and_tests(str(repo), agents_md=agents_md)
        assert langs == ["python"]  # not ["python", "rust"]
        assert tests == ["make test"]  # not ["pytest", "cargo test"]


class TestNestedDetection:
    """Detect languages from nested subdirectories (monorepo layout)."""

    def test_monorepo_python_plus_frontend(self, repo) -> None:
        """Detect both Python (root) and TypeScript (nested frontend/)."""
        (repo / "pyproject.toml").write_text("[project]\n")
        frontend = repo / "frontend"
        frontend.mkdir()
        (frontend / "package.json").write_text(json.dumps({"scripts": {"test": "vitest"}}))
        (frontend / "tsconfig.json").write_text("{}")

        langs, tests = detect_languages_and_tests(str(repo))
        assert "python" in langs
        assert "typescript" in langs
        assert "pytest" in tests
        assert any("frontend" in t and "npm test" in t for t in tests)

    def test_nested_package_json_without_tsconfig(self, repo) -> None:
        """Nested package.json without tsconfig → javascript, not typescript."""
        subdir = repo / "webapp"
        subdir.mkdir()
        (subdir / "package.json").write_text(json.dumps({"scripts": {"test": "jest"}}))

        langs, tests = detect_languages_and_tests(str(repo))
        assert "javascript" in langs
        assert "typescript" not in langs

    def test_hidden_dirs_skipped(self, repo) -> None:
        """Dotfiles/dirs like .git should not be scanned."""
        gitdir = repo / ".git"
        gitdir.mkdir()
        (gitdir / "package.json").write_text("{}")

        langs, tests = detect_languages_and_tests(str(repo))
        assert "javascript" not in langs


class TestE2EDetection:
    """Detect E2E test commands from marker files."""

    def test_playwright_config_ts(self, repo) -> None:
        (repo / "playwright.config.ts").write_text("export default {}")
        cmds = detect_e2e_tests(str(repo))
        assert cmds == ["npx playwright test"]

    def test_playwright_config_js(self, repo) -> None:
        (repo / "playwright.config.js").write_text("module.exports = {}")
        cmds = detect_e2e_tests(str(repo))
        assert cmds == ["npx playwright test"]

    def test_cypress_config(self, repo) -> None:
        (repo / "cypress.config.ts").write_text("export default {}")
        cmds = detect_e2e_tests(str(repo))
        assert cmds == ["npx cypress run"]

    def test_wdio_config(self, repo) -> None:
        (repo / "wdio.conf.ts").write_text("export const config = {}")
        cmds = detect_e2e_tests(str(repo))
        assert cmds == ["npx wdio run"]

    def test_no_e2e_markers(self, repo) -> None:
        cmds = detect_e2e_tests(str(repo))
        assert cmds == []

    def test_nested_playwright_config(self, repo) -> None:
        frontend = repo / "frontend"
        frontend.mkdir()
        (frontend / "playwright.config.ts").write_text("export default {}")
        cmds = detect_e2e_tests(str(repo))
        assert cmds == ["cd frontend && npx playwright test"]

    def test_no_duplicate_frameworks(self, repo) -> None:
        """Both .ts and .js configs for same framework should not duplicate."""
        (repo / "playwright.config.ts").write_text("export default {}")
        (repo / "playwright.config.js").write_text("module.exports = {}")
        cmds = detect_e2e_tests(str(repo))
        assert len(cmds) == 1
        assert cmds == ["npx playwright test"]

    def test_agents_md_override(self, repo) -> None:
        (repo / "playwright.config.ts").write_text("export default {}")
        cmds = detect_e2e_tests(str(repo), agents_md="## E2E test command: npm run e2e\n")
        assert cmds == ["npm run e2e"]

    def test_agents_md_none_disables(self, repo) -> None:
        (repo / "playwright.config.ts").write_text("export default {}")
        cmds = detect_e2e_tests(str(repo), agents_md="## E2E tests: none\n")
        assert cmds == []

    def test_hidden_dirs_skipped(self, repo) -> None:
        gitdir = repo / ".git"
        gitdir.mkdir()
        (gitdir / "playwright.config.ts").write_text("export default {}")
        cmds = detect_e2e_tests(str(repo))
        assert cmds == []
