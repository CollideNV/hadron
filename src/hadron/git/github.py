"""GitHub REST API client for PR creation, approval checks, and merging."""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

API_BASE = "https://api.github.com"


class GitHubAPIError(Exception):
    """Non-recoverable GitHub API error."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(f"GitHub API {status_code}: {message}")


def _token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise GitHubAPIError(0, "GITHUB_TOKEN environment variable is not set")
    return token


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def create_pull_request(
    owner: str,
    repo: str,
    head: str,
    base: str,
    title: str,
    body: str,
) -> dict[str, str | int]:
    """Create a pull request. Returns ``{"number": int, "html_url": str}``.

    If a PR already exists for the same *head* -> *base*, the existing PR is
    returned instead of raising an error.
    """
    token = _token()
    async with httpx.AsyncClient(base_url=API_BASE, headers=_headers(token)) as client:
        resp = await client.post(
            f"/repos/{owner}/{repo}/pulls",
            json={"head": head, "base": base, "title": title, "body": body},
        )

        if resp.status_code == 201:
            data = resp.json()
            return {"number": data["number"], "html_url": data["html_url"]}

        # PR already exists for this head->base
        if resp.status_code == 422:
            errors = resp.json().get("errors", [])
            already_exists = any(
                "pull request already exists" in (e.get("message", "")).lower()
                for e in errors
            )
            if already_exists:
                return await _get_existing_pr(client, owner, repo, head, base)

        raise GitHubAPIError(resp.status_code, resp.text)


async def _get_existing_pr(
    client: httpx.AsyncClient,
    owner: str,
    repo: str,
    head: str,
    base: str,
) -> dict[str, str | int]:
    """Fetch an existing open PR for *head* -> *base*."""
    resp = await client.get(
        f"/repos/{owner}/{repo}/pulls",
        params={"head": f"{owner}:{head}", "base": base, "state": "open"},
    )
    if resp.status_code != 200:
        raise GitHubAPIError(resp.status_code, resp.text)
    prs = resp.json()
    if not prs:
        raise GitHubAPIError(404, f"No open PR found for {head} -> {base}")
    return {"number": prs[0]["number"], "html_url": prs[0]["html_url"]}


async def is_pr_approved(owner: str, repo: str, pr_number: int) -> bool:
    """Return *True* if the PR has at least one APPROVED review with no
    subsequent CHANGES_REQUESTED."""
    token = _token()
    async with httpx.AsyncClient(base_url=API_BASE, headers=_headers(token)) as client:
        resp = await client.get(f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews")
        if resp.status_code != 200:
            raise GitHubAPIError(resp.status_code, resp.text)

    reviews = resp.json()
    # Walk reviews chronologically; track the latest state per reviewer
    latest: dict[str, str] = {}
    for review in reviews:
        state = review.get("state", "")
        user = review.get("user", {}).get("login", "")
        if state in ("APPROVED", "CHANGES_REQUESTED"):
            latest[user] = state

    if not latest:
        return False
    # Any outstanding CHANGES_REQUESTED means not approved
    return all(s == "APPROVED" for s in latest.values())


async def merge_pull_request(
    owner: str,
    repo: str,
    pr_number: int,
    merge_method: str = "squash",
) -> dict[str, str]:
    """Merge a pull request. Returns ``{"sha": str, "message": str}``.

    Raises :class:`GitHubAPIError` on merge conflict or other failure.
    """
    token = _token()
    async with httpx.AsyncClient(base_url=API_BASE, headers=_headers(token)) as client:
        resp = await client.put(
            f"/repos/{owner}/{repo}/pulls/{pr_number}/merge",
            json={"merge_method": merge_method},
        )

    if resp.status_code == 200:
        data = resp.json()
        return {"sha": data.get("sha", ""), "message": data.get("message", "")}

    raise GitHubAPIError(resp.status_code, resp.text)


def pr_number_from_url(pr_url: str) -> int:
    """Extract PR number from a GitHub PR URL.

    >>> pr_number_from_url("https://github.com/org/repo/pull/42")
    42
    """
    return int(pr_url.rstrip("/").split("/")[-1])
