"""WorktreeManager — git operations via subprocess for pipeline worktree management."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


async def _run_git(
    *args: str,
    cwd: str | Path | None = None,
    check: bool = True,
) -> str:
    """Run a git command and return stdout."""
    cmd = ["git"] + list(args)
    logger.debug("git %s (cwd=%s)", " ".join(args), cwd)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed (rc={proc.returncode}): {stderr.decode().strip()}"
        )
    return stdout.decode().strip()


class WorktreeManager:
    """Manages git bare clones and worktrees for pipeline runs.

    Directory layout:
        {workspace}/repos/{repo_name}/          ← bare clone (.git directory)
        {workspace}/runs/cr-{cr_id}/{repo_name}/ ← worktree on branch ai/cr-{cr_id}
    """

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace)
        self.repos_dir = self.workspace / "repos"
        self.runs_dir = self.workspace / "runs"

    def _bare_path(self, repo_name: str) -> Path:
        return self.repos_dir / repo_name

    def _worktree_path(self, cr_id: str, repo_name: str) -> Path:
        return self.runs_dir / f"cr-{cr_id}" / repo_name

    def _branch_name(self, cr_id: str) -> str:
        return f"ai/cr-{cr_id}"

    async def clone_bare(self, repo_url: str, repo_name: str) -> Path:
        """Clone a repository as a bare clone. Skips if already cloned."""
        bare_path = self._bare_path(repo_name)
        if bare_path.exists():
            logger.info("Bare clone already exists: %s", bare_path)
            await _run_git("fetch", "--all", cwd=bare_path)
            return bare_path
        bare_path.parent.mkdir(parents=True, exist_ok=True)
        await _run_git("clone", "--bare", repo_url, str(bare_path))
        return bare_path

    async def create_worktree(
        self, repo_name: str, cr_id: str, start_branch: str = "main"
    ) -> Path:
        """Create a worktree for a CR on a new feature branch.

        Creates branch ai/cr-{cr_id} from the start_branch.
        Returns the worktree path.
        """
        bare_path = self._bare_path(repo_name)
        worktree_path = self._worktree_path(cr_id, repo_name)
        branch = self._branch_name(cr_id)

        worktree_path.parent.mkdir(parents=True, exist_ok=True)

        if worktree_path.exists():
            logger.info("Worktree already exists: %s", worktree_path)
            return worktree_path

        await _run_git(
            "worktree",
            "add",
            "-b",
            branch,
            str(worktree_path),
            start_branch,
            cwd=bare_path,
        )
        return worktree_path

    async def commit_and_push(
        self, worktree_path: str | Path, message: str
    ) -> None:
        """Stage all changes, commit, and push the current branch."""
        wt = Path(worktree_path)
        await _run_git("add", "-A", cwd=wt)

        # Check if there's anything to commit
        status = await _run_git("status", "--porcelain", cwd=wt)
        if not status:
            logger.info("Nothing to commit in %s", wt)
            return

        await _run_git("commit", "-m", message, cwd=wt)
        branch = await _run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=wt)
        await _run_git("push", "origin", branch, cwd=wt)

    async def recover_from_remote(
        self, repo_url: str, repo_name: str, cr_id: str
    ) -> Path:
        """Recover a worktree by cloning and checking out an existing remote branch.

        Used when resuming a CR on a new pod.
        """
        await self.clone_bare(repo_url, repo_name)
        bare_path = self._bare_path(repo_name)
        worktree_path = self._worktree_path(cr_id, repo_name)
        branch = self._branch_name(cr_id)

        worktree_path.parent.mkdir(parents=True, exist_ok=True)

        if worktree_path.exists():
            return worktree_path

        # Check if the remote branch exists
        await _run_git("fetch", "origin", branch, cwd=bare_path, check=False)
        await _run_git(
            "worktree",
            "add",
            str(worktree_path),
            branch,
            cwd=bare_path,
        )
        return worktree_path

    async def get_diff(self, worktree_path: str | Path, base_branch: str = "main") -> str:
        """Get the diff between the current branch and base branch."""
        return await _run_git("diff", f"{base_branch}...HEAD", cwd=worktree_path)

    async def rebase(self, worktree_path: str | Path, base_branch: str = "main") -> bool:
        """Fetch and rebase onto latest base branch. Returns True if clean."""
        wt = Path(worktree_path)
        await _run_git("fetch", "origin", base_branch, cwd=wt)
        try:
            await _run_git("rebase", f"origin/{base_branch}", cwd=wt)
            return True
        except RuntimeError:
            await _run_git("rebase", "--abort", cwd=wt, check=False)
            return False

    async def get_directory_tree(self, worktree_path: str | Path, max_depth: int = 3) -> str:
        """Get a directory tree listing for context."""
        wt = Path(worktree_path)
        result = []
        for root, dirs, files in os.walk(wt):
            depth = str(root).replace(str(wt), "").count(os.sep)
            if depth >= max_depth:
                dirs.clear()
                continue
            # Skip hidden dirs and common noise
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in {"node_modules", "__pycache__", ".venv", "venv"}]
            indent = "  " * depth
            result.append(f"{indent}{os.path.basename(root)}/")
            for f in sorted(files):
                if not f.startswith("."):
                    result.append(f"{indent}  {f}")
        return "\n".join(result)
