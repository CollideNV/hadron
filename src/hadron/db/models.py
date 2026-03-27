"""ORM models for Hadron's own tables (not LangGraph checkpoint tables)."""

from __future__ import annotations

import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class CRRun(Base):
    """Tracks a single Change Request pipeline run."""

    __tablename__ = "cr_runs"

    cr_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(
        String(32), default="pending", index=True
    )  # pending | running | paused | completed | failed
    external_id: Mapped[str | None] = mapped_column(String(256), unique=True, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="api")
    raw_cr_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    config_snapshot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    repo_runs: Mapped[list[RepoRun]] = relationship(
        "RepoRun", back_populates="cr_run", lazy="selectin"
    )


class RepoRun(Base):
    """Tracks a single repo-worker within a CR.

    One CRRun → many RepoRuns (one per repo_url).
    Workers update their own RepoRun on completion.
    The Controller checks all RepoRuns to determine CR-level release readiness.
    """

    __tablename__ = "repo_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cr_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("cr_runs.cr_id"), index=True
    )
    cr_run: Mapped[CRRun] = relationship("CRRun", back_populates="repo_runs")
    repo_url: Mapped[str] = mapped_column(String(512))
    repo_name: Mapped[str] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(
        String(32), default="pending", index=True
    )  # pending | running | completed | failed | paused
    branch_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    pr_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    pr_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PromptTemplate(Base):
    """Editable prompt template for an agent role."""

    __tablename__ = "prompt_templates"

    role: Mapped[str] = mapped_column(String(64), primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(String(256), server_default="")
    version: Mapped[int] = mapped_column(default=1)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PipelineSetting(Base):
    """Key-value store for pipeline configuration (JSON values)."""

    __tablename__ = "pipeline_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AuditLog(Base):
    """Immutable audit trail for all significant actions."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cr_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(128))
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RunSummary(Base):
    """Structured summary of a single pipeline run for analytics and retrospective."""

    __tablename__ = "run_summaries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cr_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("cr_runs.cr_id"), index=True
    )
    repo_name: Mapped[str] = mapped_column(String(256), index=True)

    # Outcome
    final_status: Mapped[str] = mapped_column(String(32))
    pause_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timing
    started_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    stage_timings: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Cost
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    total_input_tokens: Mapped[int] = mapped_column(default=0)
    total_output_tokens: Mapped[int] = mapped_column(default=0)
    model_breakdown: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Loop counts
    verification_loop_count: Mapped[int] = mapped_column(default=0)
    dev_loop_count: Mapped[int] = mapped_column(default=0)
    review_loop_count: Mapped[int] = mapped_column(default=0)

    # Review findings summary
    review_findings_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Throttling
    throttle_count: Mapped[int] = mapped_column(default=0)
    throttle_seconds: Mapped[float] = mapped_column(Float, default=0.0)

    # Retrospective insights (populated by rule engine)
    retrospective_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
