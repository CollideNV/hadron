"""Tests for E2E contract building (shared PVC architecture).

With the shared-volume model, node_modules are already installed by the worker.
The contract only includes `npx playwright install chromium` to ensure the
runner's Chromium binary matches the repo's pinned @playwright/test version.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hadron.pipeline.e2e_runner import build_e2e_contract, workspace_pvc_name


def _write(base: Path, rel: str, content: str = "") -> None:
    path = base / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


@pytest.fixture
def worktree(tmp_path: Path) -> Path:
    return tmp_path


class TestPlaywrightInstallSetup:
    """Shared PVC means no npm ci/install — only chromium install for version match."""

    def test_frontend_subdir_with_lockfile(self, worktree: Path) -> None:
        _write(worktree, "frontend/playwright.config.ts", "export default {}")
        _write(worktree, "frontend/package.json", "{}")
        _write(worktree, "frontend/package-lock.json", "{}")

        contract = build_e2e_contract(
            worktree_path=str(worktree),
            command="cd frontend && npx playwright test",
            env={},
            timeout=600,
            languages=["typescript"],
        )

        # Only chromium install — no npm ci/install (deps on shared volume)
        assert "cd frontend && npx playwright install chromium" in contract.setup
        assert not any("npm ci" in s or "npm install" in s for s in contract.setup)

    def test_root_level_playwright(self, worktree: Path) -> None:
        _write(worktree, "playwright.config.ts", "export default {}")
        _write(worktree, "package.json", "{}")

        contract = build_e2e_contract(
            worktree_path=str(worktree),
            command="npx playwright test",
            env={},
            timeout=600,
            languages=["typescript"],
        )

        assert "npx playwright install chromium" in contract.setup
        assert not any("npm ci" in s or "npm install" in s for s in contract.setup)

    def test_no_playwright_config_no_setup(self, worktree: Path) -> None:
        """Without a playwright config there's nothing to install."""
        _write(worktree, "package.json", "{}")
        _write(worktree, "package-lock.json", "{}")

        contract = build_e2e_contract(
            worktree_path=str(worktree),
            command="npm test",
            env={},
            timeout=600,
            languages=["typescript"],
        )

        assert not any("playwright" in s for s in contract.setup)

    def test_config_without_package_json_is_skipped(self, worktree: Path) -> None:
        """A stray playwright.config.* with no sibling package.json contributes nothing."""
        _write(worktree, "weird/playwright.config.ts", "export default {}")

        contract = build_e2e_contract(
            worktree_path=str(worktree),
            command="cd weird && npx playwright test",
            env={},
            timeout=600,
            languages=["typescript"],
        )

        assert contract.setup == []

    def test_webserver_block_no_services(self, worktree: Path) -> None:
        """When Playwright declares webServer, no services are synthesized."""
        _write(
            worktree,
            "frontend/playwright.config.ts",
            "export default { webServer: { command: 'npm run dev' } }",
        )
        _write(worktree, "frontend/package.json", "{}")
        _write(worktree, "frontend/package-lock.json", "{}")

        contract = build_e2e_contract(
            worktree_path=str(worktree),
            command="cd frontend && npx playwright test",
            env={},
            timeout=600,
            languages=["typescript"],
        )

        assert "cd frontend && npx playwright install chromium" in contract.setup
        assert contract.services == []


class TestWorktreePathInContract:
    """Contract carries worktree_path for the runner to use as cwd."""

    def test_worktree_path_set(self, worktree: Path) -> None:
        contract = build_e2e_contract(
            worktree_path=str(worktree),
            command="npx playwright test",
            env={"FOO": "bar"},
            timeout=300,
            languages=["typescript"],
        )

        assert contract.worktree_path == str(worktree)

    def test_worktree_path_in_json(self, worktree: Path) -> None:
        import json

        contract = build_e2e_contract(
            worktree_path=str(worktree),
            command="npx playwright test",
            env={},
            timeout=600,
            languages=["typescript"],
        )

        data = json.loads(contract.to_json())
        assert data["worktree_path"] == str(worktree)


class TestWorkspacePvcName:
    """Deterministic PVC naming for shared volume."""

    def test_basic(self) -> None:
        name = workspace_pvc_name("CR-abc123", "my-repo")
        assert name == "hadron-workspace-cr-abc123-my-repo"

    def test_sanitizes_special_chars(self) -> None:
        name = workspace_pvc_name("CR_foo.bar", "some_repo/name")
        # Underscores and dots become dashes
        assert "_" not in name
        assert "." not in name
        assert "/" not in name

    def test_truncates_long_names(self) -> None:
        name = workspace_pvc_name("a" * 200, "b" * 200)
        assert len(name) <= 253


class TestServiceSynthesis:
    """Backend services synthesized when no webServer block is present."""

    def test_maven_project_gets_java_service(self, worktree: Path) -> None:
        _write(worktree, "pom.xml", "<project/>")
        _write(worktree, "frontend/playwright.config.ts", "export default {}")
        _write(worktree, "frontend/package.json", "{}")

        contract = build_e2e_contract(
            worktree_path=str(worktree),
            command="cd frontend && npx playwright test",
            env={"HADRON_TEST_BACKEND_PORT": "9090"},
            timeout=600,
            languages=["java", "typescript"],
        )

        assert any("mvn" in s for s in contract.setup)
        assert len(contract.services) == 1
        assert contract.services[0].name == "backend"
        assert contract.services[0].wait_tcp == 9090

    def test_gradle_project_gets_java_service(self, worktree: Path) -> None:
        _write(worktree, "build.gradle", "")
        _write(worktree, "frontend/playwright.config.ts", "export default {}")
        _write(worktree, "frontend/package.json", "{}")

        contract = build_e2e_contract(
            worktree_path=str(worktree),
            command="cd frontend && npx playwright test",
            env={"HADRON_TEST_BACKEND_PORT": "8080"},
            timeout=600,
            languages=["java", "typescript"],
        )

        assert any("gradlew" in s for s in contract.setup)
        assert len(contract.services) == 1
        assert contract.services[0].name == "backend"
