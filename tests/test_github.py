"""Tests for GitHub REST API client."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from hadron.git.github import (
    GitHubAPIError,
    create_pull_request,
    is_pr_approved,
    merge_pull_request,
    pr_number_from_url,
)


def _mock_response(status_code: int, json_data: dict | list | None = None, text: str = "") -> httpx.Response:
    if json_data is not None:
        content = json.dumps(json_data).encode()
        return httpx.Response(status_code, content=content, headers={"content-type": "application/json"})
    return httpx.Response(status_code, text=text)


class TestCreatePullRequest:
    async def test_success(self) -> None:
        mock_resp = _mock_response(201, {"number": 42, "html_url": "https://github.com/org/repo/pull/42"})

        with patch("hadron.git.github._token", return_value="tok"), \
             patch("hadron.git.github.httpx.AsyncClient") as MockClient:
            client = AsyncMock()
            client.post = AsyncMock(return_value=mock_resp)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await create_pull_request("org", "repo", "ai/cr-1", "main", "Title", "Body")

        assert result == {"number": 42, "html_url": "https://github.com/org/repo/pull/42"}

    async def test_already_exists_fetches_existing(self) -> None:
        error_resp = _mock_response(422, {
            "message": "Validation Failed",
            "errors": [{"message": "A pull request already exists for org:ai/cr-1."}],
        })
        existing_resp = _mock_response(200, [
            {"number": 10, "html_url": "https://github.com/org/repo/pull/10"},
        ])

        with patch("hadron.git.github._token", return_value="tok"), \
             patch("hadron.git.github.httpx.AsyncClient") as MockClient:
            client = AsyncMock()
            client.post = AsyncMock(return_value=error_resp)
            client.get = AsyncMock(return_value=existing_resp)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await create_pull_request("org", "repo", "ai/cr-1", "main", "Title", "Body")

        assert result == {"number": 10, "html_url": "https://github.com/org/repo/pull/10"}

    async def test_422_not_duplicate_raises(self) -> None:
        error_resp = _mock_response(422, {
            "message": "Validation Failed",
            "errors": [{"message": "Some other error"}],
        })

        with patch("hadron.git.github._token", return_value="tok"), \
             patch("hadron.git.github.httpx.AsyncClient") as MockClient:
            client = AsyncMock()
            client.post = AsyncMock(return_value=error_resp)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(GitHubAPIError, match="422"):
                await create_pull_request("org", "repo", "ai/cr-1", "main", "T", "B")

    async def test_500_raises(self) -> None:
        error_resp = _mock_response(500, text="Internal Server Error")

        with patch("hadron.git.github._token", return_value="tok"), \
             patch("hadron.git.github.httpx.AsyncClient") as MockClient:
            client = AsyncMock()
            client.post = AsyncMock(return_value=error_resp)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(GitHubAPIError, match="500"):
                await create_pull_request("org", "repo", "ai/cr-1", "main", "T", "B")

    async def test_missing_token_raises(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(GitHubAPIError, match="GITHUB_TOKEN"):
                await create_pull_request("org", "repo", "ai/cr-1", "main", "T", "B")


class TestIsPrApproved:
    async def test_approved(self) -> None:
        reviews = [
            {"state": "APPROVED", "user": {"login": "alice"}},
        ]
        mock_resp = _mock_response(200, reviews)

        with patch("hadron.git.github._token", return_value="tok"), \
             patch("hadron.git.github.httpx.AsyncClient") as MockClient:
            client = AsyncMock()
            client.get = AsyncMock(return_value=mock_resp)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            assert await is_pr_approved("org", "repo", 42) is True

    async def test_changes_requested_after_approval(self) -> None:
        reviews = [
            {"state": "APPROVED", "user": {"login": "alice"}},
            {"state": "CHANGES_REQUESTED", "user": {"login": "alice"}},
        ]
        mock_resp = _mock_response(200, reviews)

        with patch("hadron.git.github._token", return_value="tok"), \
             patch("hadron.git.github.httpx.AsyncClient") as MockClient:
            client = AsyncMock()
            client.get = AsyncMock(return_value=mock_resp)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            assert await is_pr_approved("org", "repo", 42) is False

    async def test_no_reviews(self) -> None:
        mock_resp = _mock_response(200, [])

        with patch("hadron.git.github._token", return_value="tok"), \
             patch("hadron.git.github.httpx.AsyncClient") as MockClient:
            client = AsyncMock()
            client.get = AsyncMock(return_value=mock_resp)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            assert await is_pr_approved("org", "repo", 42) is False

    async def test_multiple_reviewers_one_unapproved(self) -> None:
        reviews = [
            {"state": "APPROVED", "user": {"login": "alice"}},
            {"state": "CHANGES_REQUESTED", "user": {"login": "bob"}},
        ]
        mock_resp = _mock_response(200, reviews)

        with patch("hadron.git.github._token", return_value="tok"), \
             patch("hadron.git.github.httpx.AsyncClient") as MockClient:
            client = AsyncMock()
            client.get = AsyncMock(return_value=mock_resp)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            assert await is_pr_approved("org", "repo", 42) is False

    async def test_re_approved_after_changes(self) -> None:
        reviews = [
            {"state": "CHANGES_REQUESTED", "user": {"login": "alice"}},
            {"state": "APPROVED", "user": {"login": "alice"}},
        ]
        mock_resp = _mock_response(200, reviews)

        with patch("hadron.git.github._token", return_value="tok"), \
             patch("hadron.git.github.httpx.AsyncClient") as MockClient:
            client = AsyncMock()
            client.get = AsyncMock(return_value=mock_resp)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            assert await is_pr_approved("org", "repo", 42) is True


class TestMergePullRequest:
    async def test_success(self) -> None:
        mock_resp = _mock_response(200, {"sha": "abc123", "message": "Pull Request successfully merged"})

        with patch("hadron.git.github._token", return_value="tok"), \
             patch("hadron.git.github.httpx.AsyncClient") as MockClient:
            client = AsyncMock()
            client.put = AsyncMock(return_value=mock_resp)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await merge_pull_request("org", "repo", 42)

        assert result["sha"] == "abc123"

    async def test_conflict_raises(self) -> None:
        mock_resp = _mock_response(405, text="merge conflict")

        with patch("hadron.git.github._token", return_value="tok"), \
             patch("hadron.git.github.httpx.AsyncClient") as MockClient:
            client = AsyncMock()
            client.put = AsyncMock(return_value=mock_resp)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(GitHubAPIError, match="405"):
                await merge_pull_request("org", "repo", 42)


class TestPrNumberFromUrl:
    def test_standard_url(self) -> None:
        assert pr_number_from_url("https://github.com/org/repo/pull/42") == 42

    def test_trailing_slash(self) -> None:
        assert pr_number_from_url("https://github.com/org/repo/pull/99/") == 99
