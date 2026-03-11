"""Change Request models — Pydantic schemas for API input/output."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

# Shell metacharacters that must never appear in test commands.
_SHELL_METACHAR_RE = re.compile(r"[;|`\n]|\$\(|&&|\|\||>>?|<")

# Allowed base commands (before any flags/args).
_ALLOWED_TEST_COMMANDS: list[str] = [
    "pytest",
    "python -m pytest",
    "npm test",
    "npm run test",
    "npx jest",
    "yarn test",
    "pnpm test",
    "go test",
    "cargo test",
    "mvn test",
    "mvn verify",
    "gradle test",
    "gradlew test",
    "./gradlew test",
    "make test",
    "make check",
    "bundle exec rspec",
    "phpunit",
    "dotnet test",
]


def validate_test_command(cmd: str) -> str:
    """Validate a single test command string.

    Rejects shell metacharacters and unknown base commands.
    Returns the cleaned command, or raises ValueError.
    """
    cmd = cmd.strip()
    if not cmd:
        raise ValueError("test_command must not be empty")

    if _SHELL_METACHAR_RE.search(cmd):
        raise ValueError(
            "test_command contains disallowed shell metacharacters"
        )

    for allowed in sorted(_ALLOWED_TEST_COMMANDS, key=len, reverse=True):
        if cmd == allowed or cmd.startswith(allowed + " "):
            return cmd

    raise ValueError(
        f"test_command must start with one of: {', '.join(sorted(_ALLOWED_TEST_COMMANDS))}"
    )


class RawChangeRequest(BaseModel):
    """Incoming change request as received from any source connector."""

    title: str = Field(..., min_length=1, max_length=500)
    description: str = Field(..., min_length=1)
    source: str = Field(default="api", pattern=r"^(api|jira|github|ado|slack)$")
    external_id: str | None = None
    external_url: str | None = None
    repo_urls: list[str] = Field(
        default_factory=list,
        description="Target repository URLs. One worker is spawned per repo.",
    )
    repo_default_branch: str = Field(default="main")

    @field_validator("repo_urls")
    @classmethod
    def validate_repo_urls(cls, v: list[str]) -> list[str]:
        """Ensure all repo URLs use HTTPS scheme. Rejects file://, ssh://, git:// etc."""
        for url in v:
            if not url.startswith("https://"):
                raise ValueError(
                    f"Only HTTPS repository URLs are allowed, got: {url!r}"
                )
        return v


class StructuredChangeRequest(BaseModel):
    """Parsed and normalised change request — output of Intake agent."""

    title: str
    description: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    affected_domains: list[str] = Field(default_factory=list)
    priority: str = Field(default="medium", pattern=r"^(low|medium|high|critical)$")
    constraints: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
