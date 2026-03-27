"""add run_summaries table

Revision ID: e6a3b7c9d2f1
Revises: d5e9f3a2b8c1
Create Date: 2026-03-27 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e6a3b7c9d2f1"
down_revision: Union[str, None] = "d5e9f3a2b8c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "run_summaries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cr_id", sa.String(64), sa.ForeignKey("cr_runs.cr_id"), nullable=False),
        sa.Column("repo_name", sa.String(256), nullable=False),
        # Outcome
        sa.Column("final_status", sa.String(32), nullable=False),
        sa.Column("pause_reason", sa.String(64), nullable=True),
        sa.Column("error_category", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        # Timing
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column("stage_timings", sa.JSON(), nullable=True),
        # Cost
        sa.Column("total_cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("total_input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("model_breakdown", sa.JSON(), nullable=True),
        # Loop counts
        sa.Column("verification_loop_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dev_loop_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("review_loop_count", sa.Integer(), nullable=False, server_default="0"),
        # Review
        sa.Column("review_findings_summary", sa.JSON(), nullable=True),
        # Throttling
        sa.Column("throttle_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("throttle_seconds", sa.Float(), nullable=False, server_default="0"),
        # Retrospective
        sa.Column("retrospective_json", sa.JSON(), nullable=True),
        # Meta
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_run_summaries_cr_id", "run_summaries", ["cr_id"])
    op.create_index("ix_run_summaries_repo_name", "run_summaries", ["repo_name"])
    op.create_index("ix_run_summaries_created_status", "run_summaries", ["created_at", "final_status"])


def downgrade() -> None:
    op.drop_index("ix_run_summaries_created_status", table_name="run_summaries")
    op.drop_index("ix_run_summaries_repo_name", table_name="run_summaries")
    op.drop_index("ix_run_summaries_cr_id", table_name="run_summaries")
    op.drop_table("run_summaries")
