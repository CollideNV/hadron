"""Tests for git URL parsing utilities."""

from __future__ import annotations

import pytest

from hadron.git.url import extract_owner_repo, extract_repo_name


class TestExtractRepoName:
    def test_https(self) -> None:
        assert extract_repo_name("https://github.com/org/repo") == "repo"

    def test_https_with_git_suffix(self) -> None:
        assert extract_repo_name("https://github.com/org/repo.git") == "repo"

    def test_ssh(self) -> None:
        assert extract_repo_name("git@github.com:org/repo.git") == "repo"

    def test_trailing_slash(self) -> None:
        assert extract_repo_name("https://github.com/org/repo/") == "repo"


class TestExtractOwnerRepo:
    def test_https(self) -> None:
        assert extract_owner_repo("https://github.com/org/repo") == ("org", "repo")

    def test_https_with_git_suffix(self) -> None:
        assert extract_owner_repo("https://github.com/org/repo.git") == ("org", "repo")

    def test_ssh(self) -> None:
        assert extract_owner_repo("git@github.com:org/repo.git") == ("org", "repo")

    def test_trailing_slash(self) -> None:
        assert extract_owner_repo("https://github.com/org/repo/") == ("org", "repo")

    def test_nested_path(self) -> None:
        assert extract_owner_repo("https://gitlab.com/group/subgroup/repo.git") == ("subgroup", "repo")

    def test_invalid_url_raises(self) -> None:
        with pytest.raises(ValueError, match="Cannot extract"):
            extract_owner_repo("https://github.com/solo")
