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


def extract_owner_repo(url: str) -> tuple[str, str]:
    """Extract (owner, repo) from a git URL.

    Examples:
        >>> extract_owner_repo("https://github.com/org/repo")
        ('org', 'repo')
        >>> extract_owner_repo("https://github.com/org/repo.git")
        ('org', 'repo')
        >>> extract_owner_repo("git@github.com:org/repo.git")
        ('org', 'repo')
    """
    url = url.rstrip("/")
    # SSH URLs use ':' as path separator
    if ":" in url and not url.startswith("http"):
        path = url.rsplit(":", 1)[-1]
    else:
        # HTTPS — strip scheme + host to get the path portion
        # e.g. "https://github.com/org/repo.git" -> "org/repo.git"
        parts = url.split("/")
        # Find the portion after the host (scheme://host/...)
        try:
            host_idx = next(i for i, p in enumerate(parts) if p and "." in p)
            path = "/".join(parts[host_idx + 1 :])
        except StopIteration:
            path = ""
    if path.endswith(".git"):
        path = path[:-4]
    segments = path.split("/")
    if len(segments) < 2 or not segments[-1] or not segments[-2]:
        raise ValueError(f"Cannot extract owner/repo from URL: {url}")
    return segments[-2], segments[-1]
