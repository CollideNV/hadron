"""Git URL parsing utilities."""

from __future__ import annotations


def extract_repo_name(url: str) -> str:
    """Extract the repository name from a git URL.

    Handles HTTPS and SSH URLs, with or without .git suffix.

    Examples:
        >>> extract_repo_name("https://github.com/org/repo")
        'repo'
        >>> extract_repo_name("https://github.com/org/repo.git")
        'repo'
        >>> extract_repo_name("git@github.com:org/repo.git")
        'repo'
    """
    url = url.rstrip("/")
    # SSH URLs use ':' as path separator
    if ":" in url and not url.startswith("http"):
        url = url.rsplit(":", 1)[-1]
    name = url.split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return name
