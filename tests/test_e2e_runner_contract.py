"""Tests for E2E contract building (npm install + chromium setup steps)."""

from __future__ import annotations

from pathlib import Path

import pytest

from hadron.pipeline.e2e_runner import build_e2e_contract


def _write(base: Path, rel: str, content: str = "") -> None:
    path = base / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


@pytest.fixture
def worktree(tmp_path: Path) -> Path:
    return tmp_path


class TestNpmInstallSetup:
    """`node_modules` is excluded from the tarball — the contract must include
    `npm ci` for every dir that pairs a playwright.config.* with a package.json,
    otherwise the runner's `npx playwright test` fails with ERR_MODULE_NOT_FOUND.
    """

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

        assert "cd frontend && npm ci" in contract.setup
        assert "cd frontend && npx playwright install chromium" in contract.setup
        # npm ci must precede the chromium install (playwright CLI needs the dep).
        assert contract.setup.index("cd frontend && npm ci") < \
            contract.setup.index("cd frontend && npx playwright install chromium")

    def test_root_level_playwright_without_lockfile_uses_npm_install(
        self, worktree: Path
    ) -> None:
        _write(worktree, "playwright.config.ts", "export default {}")
        _write(worktree, "package.json", "{}")
        # No package-lock.json — fall back to `npm install`.

        contract = build_e2e_contract(
            worktree_path=str(worktree),
            command="npx playwright test",
            env={},
            timeout=600,
            languages=["typescript"],
        )

        assert "npm install" in contract.setup
        assert "npx playwright install chromium" in contract.setup
        assert "npm ci" not in contract.setup

    def test_no_playwright_config_no_npm_setup(self, worktree: Path) -> None:
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

        # No playwright config anywhere → no npm setup is synthesized.
        assert not any("npm ci" in s or "npm install" in s for s in contract.setup)
        assert not any("playwright install" in s for s in contract.setup)

    def test_config_without_package_json_is_skipped(self, worktree: Path) -> None:
        """A stray playwright.config.* with no sibling package.json contributes nothing."""
        _write(worktree, "weird/playwright.config.ts", "export default {}")
        # Intentionally no weird/package.json.

        contract = build_e2e_contract(
            worktree_path=str(worktree),
            command="cd weird && npx playwright test",
            env={},
            timeout=600,
            languages=["typescript"],
        )

        assert not any("npm" in s for s in contract.setup)

    def test_webserver_block_still_gets_npm_install(self, worktree: Path) -> None:
        """Even when Playwright owns server lifecycle (webServer block), we
        still need node_modules locally for @playwright/test to resolve."""
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

        assert "cd frontend && npm ci" in contract.setup
        # webServer present → no synthesized services.
        assert contract.services == []
