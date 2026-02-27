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


class RawChangeRequest(BaseModel):
    """Incoming change request as received from any source connector."""

    title: str = Field(..., min_length=1, max_length=500)
    description: str = Field(..., min_length=1)
    source: str = Field(default="api", pattern=r"^(api|jira|github|ado|slack)$")
    external_id: str | None = None
    external_url: str | None = None
    repo_url: str | None = Field(
        default=None,
        description="Target repository URL. Required for MVP (single-repo).",
    )
    repo_default_branch: str = Field(default="main")
    test_command: str = Field(
        default="pytest",
        description="Command to run the repo's test suite.",
    )
    language: str = Field(
        default="python",
        description="Primary language of the target repo.",
    )

    @field_validator("test_command", mode="before")
    @classmethod
    def validate_test_command(cls, v: str) -> str:
        v = v.strip()
        if not v:
            return "pytest"

        if _SHELL_METACHAR_RE.search(v):
            raise ValueError(
                "test_command contains disallowed shell metacharacters"
            )

        # Check that the command starts with an allowed base command
        for allowed in sorted(_ALLOWED_TEST_COMMANDS, key=len, reverse=True):
            if v == allowed or v.startswith(allowed + " "):
                return v

        raise ValueError(
            f"test_command must start with one of: {', '.join(sorted(_ALLOWED_TEST_COMMANDS))}"
        )


class StructuredChangeRequest(BaseModel):
    """Parsed and normalised change request — output of Intake agent."""

    title: str
    description: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    affected_domains: list[str] = Field(default_factory=list)
    priority: str = Field(default="medium", pattern=r"^(low|medium|high|critical)$")
    constraints: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
