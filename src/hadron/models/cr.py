"""Change Request models — Pydantic schemas for API input/output."""

from __future__ import annotations

from pydantic import BaseModel, Field


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
    model: str | None = Field(
        default=None,
        description="Model override for the pipeline (e.g. gemini-3-pro-preview).",
    )

    @field_validator("agent_model")
    @classmethod
    def validate_agent_model(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not any(v.startswith(prefix) for prefix in _KNOWN_MODEL_PREFIXES):
            raise ValueError(
                f"agent_model must start with one of: {', '.join(_KNOWN_MODEL_PREFIXES)}"
            )
        return v

    @field_validator("repo_urls")
    @classmethod
    def validate_repo_urls(cls, v: list[str]) -> list[str]:
        """Validate repo URLs.

        Allows HTTPS URLs for hosted repos and local filesystem paths
        (for development/testing). Rejects file://, ssh://, git:// schemes.
        """
        for url in v:
            if "://" in url and not url.startswith("https://"):
                raise ValueError(
                    f"Only HTTPS repository URLs or local paths are allowed, got: {url!r}"
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
