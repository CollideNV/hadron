"""Tests for WorktreeManager and git subprocess helpers."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hadron.git.worktree import WorktreeManager, _run_git, _sanitize_git_output


# ---------------------------------------------------------------------------
# _sanitize_git_output
# ---------------------------------------------------------------------------


class TestSanitizeGitOutput:
    def test_strips_token_from_https_url(self) -> None:
        text = "fatal: could not read from https://ghp_abc123@github.com/org/repo"
        result = _sanitize_git_output(text)
        assert "ghp_abc123" not in result
        assert "://***@github.com" in result

    def test_strips_user_pass_from_url(self) -> None:
        text = "https://user:password@example.com/repo.git"
        result = _sanitize_git_output(text)
        assert "user:password" not in result
        assert "://***@example.com" in result

    def test_preserves_text_without_credentials(self) -> None:
        text = "Already up to date."
        assert _sanitize_git_output(text) == text

    def test_strips_multiple_credentials(self) -> None:
        text = "https://tok1@a.com and https://tok2@b.com"
        result = _sanitize_git_output(text)
        assert "tok1" not in result
        assert "tok2" not in result

    def test_empty_string(self) -> None:
        assert _sanitize_git_output("") == ""


# ---------------------------------------------------------------------------
# _run_git
# ---------------------------------------------------------------------------


class TestRunGit:
    @pytest.mark.asyncio
    async def test_returns_stdout_on_success(self) -> None:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"output text\n", b""))

        with patch("hadron.git.worktree.asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await _run_git("status", cwd="/tmp")

        assert result == "output text"

    @pytest.mark.asyncio
    async def test_raises_on_failure_with_sanitized_stderr(self) -> None:
        mock_proc = MagicMock()
        mock_proc.returncode = 128
        mock_proc.communicate = AsyncMock(
            return_value=(b"", b"fatal: https://token123@github.com not found\n")
        )

        with patch("hadron.git.worktree.asyncio.create_subprocess_exec", return_value=mock_proc):
            with pytest.raises(RuntimeError, match="failed.*rc=128"):
                await _run_git("clone", "repo")

    @pytest.mark.asyncio
    async def test_error_message_does_not_leak_token(self) -> None:
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(
            return_value=(b"", b"https://ghp_secret@github.com/org/repo\n")
        )

        with patch("hadron.git.worktree.asyncio.create_subprocess_exec", return_value=mock_proc):
            with pytest.raises(RuntimeError) as exc_info:
                await _run_git("fetch")
            assert "ghp_secret" not in str(exc_info.value)
            assert "***" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_check_false_does_not_raise(self) -> None:
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"some output", b"some error"))

        with patch("hadron.git.worktree.asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await _run_git("diff", check=False)

        assert result == "some output"


# ---------------------------------------------------------------------------
# WorktreeManager._sanitize_name
# ---------------------------------------------------------------------------


class TestSanitizeName:
    def test_replaces_forward_slash(self) -> None:
        assert WorktreeManager._sanitize_name("org/repo") == "org_repo"

    def test_replaces_backslash(self) -> None:
        assert WorktreeManager._sanitize_name("org\\repo") == "org_repo"

    def test_replaces_dotdot(self) -> None:
        assert WorktreeManager._sanitize_name("..foo") == "_foo"

    def test_rejects_empty_string(self) -> None:
        with pytest.raises(ValueError, match="Invalid name"):
            WorktreeManager._sanitize_name("")

    def test_rejects_dot_starting_name(self) -> None:
        with pytest.raises(ValueError, match="Invalid name"):
            WorktreeManager._sanitize_name(".hidden")

    def test_rejects_all_slashes(self) -> None:
        # "///" becomes "___" which is fine
        result = WorktreeManager._sanitize_name("///")
        assert result == "___"

    def test_plain_name_unchanged(self) -> None:
        assert WorktreeManager._sanitize_name("my-repo") == "my-repo"

    def test_mixed_separators(self) -> None:
        assert WorktreeManager._sanitize_name("a/b\\c..d") == "a_b_c_d"


# ---------------------------------------------------------------------------
# WorktreeManager path methods
# ---------------------------------------------------------------------------


class TestPathMethods:
    def test_bare_path(self, tmp_path: Path) -> None:
        wm = WorktreeManager(tmp_path)
        assert wm._bare_path("my-repo") == tmp_path / "repos" / "my-repo"

    def test_bare_path_sanitizes(self, tmp_path: Path) -> None:
        wm = WorktreeManager(tmp_path)
        assert wm._bare_path("org/repo") == tmp_path / "repos" / "org_repo"

    def test_worktree_path(self, tmp_path: Path) -> None:
        wm = WorktreeManager(tmp_path)
        result = wm._worktree_path("123", "my-repo")
        assert result == tmp_path / "runs" / "cr-123" / "my-repo"

    def test_worktree_path_sanitizes(self, tmp_path: Path) -> None:
        wm = WorktreeManager(tmp_path)
        result = wm._worktree_path("../evil", "org/repo")
        assert result == tmp_path / "runs" / "cr-__evil" / "org_repo"

    def test_branch_name(self, tmp_path: Path) -> None:
        wm = WorktreeManager(tmp_path)
        assert wm._branch_name("42") == "ai/cr-42"


# ---------------------------------------------------------------------------
# WorktreeManager.clone_bare
# ---------------------------------------------------------------------------


class TestCloneBare:
    @pytest.mark.asyncio
    async def test_clones_when_not_exists(self, tmp_path: Path) -> None:
        wm = WorktreeManager(tmp_path)

        with patch("hadron.git.worktree._run_git", new_callable=AsyncMock) as mock_git:
            result = await wm.clone_bare("https://github.com/org/repo.git", "my-repo")

        expected_path = tmp_path / "repos" / "my-repo"
        assert result == expected_path
        assert mock_git.call_count == 2
        mock_git.assert_any_call(
            "clone", "--bare", "https://github.com/org/repo.git", str(expected_path)
        )
        mock_git.assert_any_call(
            "config", "remote.origin.fetch",
            "+refs/heads/*:refs/heads/*",
            cwd=expected_path,
        )

    @pytest.mark.asyncio
    async def test_fetches_when_already_exists(self, tmp_path: Path) -> None:
        wm = WorktreeManager(tmp_path)
        bare_path = tmp_path / "repos" / "my-repo"
        bare_path.mkdir(parents=True)

        with patch("hadron.git.worktree._run_git", new_callable=AsyncMock) as mock_git:
            result = await wm.clone_bare("https://github.com/org/repo.git", "my-repo")

        assert result == bare_path
        assert mock_git.call_count == 2
        mock_git.assert_any_call(
            "config", "remote.origin.fetch",
            "+refs/heads/*:refs/heads/*",
            cwd=bare_path, check=False,
        )
        mock_git.assert_any_call("fetch", "--all", "--prune", cwd=bare_path)

    @pytest.mark.asyncio
    async def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        wm = WorktreeManager(tmp_path)

        with patch("hadron.git.worktree._run_git", new_callable=AsyncMock):
            await wm.clone_bare("https://github.com/org/repo.git", "my-repo")

        assert (tmp_path / "repos").exists()


# ---------------------------------------------------------------------------
# WorktreeManager.create_worktree
# ---------------------------------------------------------------------------


class TestCreateWorktree:
    @pytest.mark.asyncio
    async def test_creates_worktree_on_feature_branch(self, tmp_path: Path) -> None:
        wm = WorktreeManager(tmp_path)
        bare_path = tmp_path / "repos" / "my-repo"
        bare_path.mkdir(parents=True)

        with patch("hadron.git.worktree._run_git", new_callable=AsyncMock) as mock_git:
            result = await wm.create_worktree("my-repo", "42")

        expected_wt = tmp_path / "runs" / "cr-42" / "my-repo"
        assert result == expected_wt
        mock_git.assert_called_once_with(
            "worktree", "add", "-b", "ai/cr-42",
            str(expected_wt), "main",
            cwd=bare_path,
        )

    @pytest.mark.asyncio
    async def test_uses_custom_start_branch(self, tmp_path: Path) -> None:
        wm = WorktreeManager(tmp_path)
        bare_path = tmp_path / "repos" / "my-repo"
        bare_path.mkdir(parents=True)

        with patch("hadron.git.worktree._run_git", new_callable=AsyncMock) as mock_git:
            await wm.create_worktree("my-repo", "42", start_branch="develop")

        call_args = mock_git.call_args
        assert call_args[0][-1] == "develop"

    @pytest.mark.asyncio
    async def test_skips_when_worktree_exists(self, tmp_path: Path) -> None:
        wm = WorktreeManager(tmp_path)
        wt_path = tmp_path / "runs" / "cr-42" / "my-repo"
        wt_path.mkdir(parents=True)

        with patch("hadron.git.worktree._run_git", new_callable=AsyncMock) as mock_git:
            result = await wm.create_worktree("my-repo", "42")

        assert result == wt_path
        mock_git.assert_not_called()


# ---------------------------------------------------------------------------
# WorktreeManager.commit_and_push
# ---------------------------------------------------------------------------


class TestCommitAndPush:
    @pytest.mark.asyncio
    async def test_stages_commits_and_pushes(self, tmp_path: Path) -> None:
        wm = WorktreeManager(tmp_path)
        wt = tmp_path / "worktree"
        wt.mkdir()

        call_count = 0

        async def mock_run_git(*args, cwd=None, check=True):
            nonlocal call_count
            call_count += 1
            cmd_str = " ".join(args)
            if "status --porcelain" in cmd_str:
                return "M file.py"
            if "rev-parse --abbrev-ref HEAD" in cmd_str:
                return "ai/cr-42"
            return ""

        with patch("hadron.git.worktree._run_git", side_effect=mock_run_git) as mock_git:
            await wm.commit_and_push(wt, "feat: add feature")

        calls = [c[0] for c in mock_git.call_args_list]
        assert calls[0] == ("add", "-A", "--", ".")
        assert calls[1] == ("status", "--porcelain")
        assert calls[2] == ("commit", "-m", "feat: add feature")
        assert calls[3] == ("rev-parse", "--abbrev-ref", "HEAD")
        assert calls[4] == ("push", "origin", "ai/cr-42")

    @pytest.mark.asyncio
    async def test_skips_commit_when_nothing_to_commit(self, tmp_path: Path) -> None:
        wm = WorktreeManager(tmp_path)
        wt = tmp_path / "worktree"
        wt.mkdir()

        async def mock_run_git(*args, cwd=None, check=True):
            if "status" in args:
                return ""
            return ""

        with patch("hadron.git.worktree._run_git", side_effect=mock_run_git) as mock_git:
            await wm.commit_and_push(wt, "feat: nothing")

        # Should call add + status (skipping commit), then push
        calls = [c[0] for c in mock_git.call_args_list]
        assert len(calls) == 4
        assert calls[0] == ("add", "-A", "--", ".")
        assert calls[1] == ("status", "--porcelain")
        # No commit call — skipped because nothing to commit
        assert calls[2] == ("rev-parse", "--abbrev-ref", "HEAD")
        assert calls[3] == ("push", "origin", "")


# ---------------------------------------------------------------------------
# WorktreeManager.get_diff
# ---------------------------------------------------------------------------


class TestGetDiff:
    @pytest.mark.asyncio
    async def test_returns_diff_output(self, tmp_path: Path) -> None:
        wm = WorktreeManager(tmp_path)
        wt = tmp_path / "worktree"

        with patch("hadron.git.worktree._run_git", new_callable=AsyncMock, return_value="diff output") as mock_git:
            result = await wm.get_diff(wt)

        assert result == "diff output"
        mock_git.assert_called_once_with("diff", "main...HEAD", cwd=wt)

    @pytest.mark.asyncio
    async def test_custom_base_branch(self, tmp_path: Path) -> None:
        wm = WorktreeManager(tmp_path)
        wt = tmp_path / "worktree"

        with patch("hadron.git.worktree._run_git", new_callable=AsyncMock, return_value="") as mock_git:
            await wm.get_diff(wt, base_branch="develop")

        mock_git.assert_called_once_with("diff", "develop...HEAD", cwd=wt)


# ---------------------------------------------------------------------------
# WorktreeManager.rebase
# ---------------------------------------------------------------------------


class TestRebase:
    @pytest.mark.asyncio
    async def test_returns_true_on_clean_rebase(self, tmp_path: Path) -> None:
        wm = WorktreeManager(tmp_path)
        wt = tmp_path / "worktree"

        with patch("hadron.git.worktree._run_git", new_callable=AsyncMock):
            result = await wm.rebase(wt)

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_on_conflict_and_aborts(self, tmp_path: Path) -> None:
        wm = WorktreeManager(tmp_path)
        wt = tmp_path / "worktree"

        async def mock_run_git(*args, cwd=None, check=True):
            if args[0] == "rebase" and "--abort" not in args:
                raise RuntimeError("conflict")
            return ""

        with patch("hadron.git.worktree._run_git", side_effect=mock_run_git) as mock_git:
            result = await wm.rebase(wt)

        assert result is False
        # Verify abort was called
        abort_call = mock_git.call_args_list[-1]
        assert abort_call[0] == ("rebase", "--abort")
        assert abort_call[1]["check"] is False

    @pytest.mark.asyncio
    async def test_fetches_before_rebase(self, tmp_path: Path) -> None:
        wm = WorktreeManager(tmp_path)
        wt = tmp_path / "worktree"

        with patch("hadron.git.worktree._run_git", new_callable=AsyncMock) as mock_git:
            await wm.rebase(wt, base_branch="develop")

        first_call = mock_git.call_args_list[0]
        assert first_call[0] == ("fetch", "origin", "develop")


# ---------------------------------------------------------------------------
# WorktreeManager.rebase_keep_conflicts
# ---------------------------------------------------------------------------


class TestRebaseKeepConflicts:
    @pytest.mark.asyncio
    async def test_returns_true_on_clean_rebase(self, tmp_path: Path) -> None:
        wm = WorktreeManager(tmp_path)
        wt = tmp_path / "worktree"

        with patch("hadron.git.worktree._run_git", new_callable=AsyncMock):
            result = await wm.rebase_keep_conflicts(wt)

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_on_conflict_without_aborting(self, tmp_path: Path) -> None:
        wm = WorktreeManager(tmp_path)
        wt = tmp_path / "worktree"

        async def mock_run_git(*args, cwd=None, check=True):
            if args[0] == "rebase" and args[1].startswith("origin/"):
                raise RuntimeError("conflict")
            return ""

        with patch("hadron.git.worktree._run_git", side_effect=mock_run_git) as mock_git:
            result = await wm.rebase_keep_conflicts(wt)

        assert result is False
        # Verify abort was NOT called (unlike regular rebase)
        call_args_list = [c[0] for c in mock_git.call_args_list]
        assert ("rebase", "--abort") not in call_args_list


# ---------------------------------------------------------------------------
# WorktreeManager.get_directory_tree
# ---------------------------------------------------------------------------


class TestGetDirectoryTree:
    @pytest.mark.asyncio
    async def test_lists_files_and_dirs(self, tmp_path: Path) -> None:
        wm = WorktreeManager(tmp_path)
        wt = tmp_path / "project"
        wt.mkdir()
        (wt / "src").mkdir()
        (wt / "src" / "main.py").write_text("print('hello')")
        (wt / "README.md").write_text("# Hello")

        result = await wm.get_directory_tree(wt)

        assert "project/" in result
        assert "src/" in result
        assert "main.py" in result
        assert "README.md" in result

    @pytest.mark.asyncio
    async def test_skips_hidden_dirs(self, tmp_path: Path) -> None:
        wm = WorktreeManager(tmp_path)
        wt = tmp_path / "project"
        wt.mkdir()
        (wt / ".git").mkdir()
        (wt / ".git" / "config").write_text("stuff")
        (wt / "visible.txt").write_text("hi")

        result = await wm.get_directory_tree(wt)

        assert ".git" not in result
        assert "visible.txt" in result

    @pytest.mark.asyncio
    async def test_skips_hidden_files(self, tmp_path: Path) -> None:
        wm = WorktreeManager(tmp_path)
        wt = tmp_path / "project"
        wt.mkdir()
        (wt / ".env").write_text("SECRET=x")
        (wt / "app.py").write_text("code")

        result = await wm.get_directory_tree(wt)

        assert ".env" not in result
        assert "app.py" in result

    @pytest.mark.asyncio
    async def test_skips_noise_dirs(self, tmp_path: Path) -> None:
        wm = WorktreeManager(tmp_path)
        wt = tmp_path / "project"
        wt.mkdir()
        (wt / "node_modules").mkdir()
        (wt / "node_modules" / "pkg.json").write_text("{}")
        (wt / "__pycache__").mkdir()
        (wt / "__pycache__" / "mod.pyc").write_bytes(b"\x00")

        result = await wm.get_directory_tree(wt)

        assert "node_modules" not in result
        assert "__pycache__" not in result

    @pytest.mark.asyncio
    async def test_respects_max_depth(self, tmp_path: Path) -> None:
        wm = WorktreeManager(tmp_path)
        wt = tmp_path / "project"
        wt.mkdir()
        (wt / "a").mkdir()
        (wt / "a" / "b").mkdir()
        (wt / "a" / "b" / "c").mkdir()
        (wt / "a" / "b" / "c" / "deep.txt").write_text("deep")
        (wt / "a" / "b" / "shallow.txt").write_text("shallow")

        result = await wm.get_directory_tree(wt, max_depth=2)

        # depth 0 = project/, depth 1 = a/, depth 2 = b/ (cut off here)
        assert "shallow.txt" not in result
        assert "deep.txt" not in result

    @pytest.mark.asyncio
    async def test_empty_directory(self, tmp_path: Path) -> None:
        wm = WorktreeManager(tmp_path)
        wt = tmp_path / "empty"
        wt.mkdir()

        result = await wm.get_directory_tree(wt)

        assert "empty/" in result

    @pytest.mark.asyncio
    async def test_indentation_reflects_depth(self, tmp_path: Path) -> None:
        wm = WorktreeManager(tmp_path)
        wt = tmp_path / "project"
        wt.mkdir()
        (wt / "sub").mkdir()
        (wt / "sub" / "file.txt").write_text("content")

        result = await wm.get_directory_tree(wt)
        lines = result.split("\n")

        # Root dir has no indent
        assert lines[0] == "project/"
        # Subdirectory has 2-space indent
        sub_line = [l for l in lines if "sub/" in l][0]
        assert sub_line == "  sub/"
        # File in subdirectory has 4-space indent
        file_line = [l for l in lines if "file.txt" in l][0]
        assert file_line == "    file.txt"
