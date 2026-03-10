"""add repo_runs table

Revision ID: a3f1c2d4e5b6
Revises: 96dd58f6d850
Create Date: 2026-03-10 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a3f1c2d4e5b6"
down_revision: Union[str, Sequence[str], None] = "96dd58f6d850"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "repo_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("cr_id", sa.String(64), nullable=False, index=True),
        sa.Column("repo_url", sa.String(512), nullable=False),
        sa.Column("repo_name", sa.String(256), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending", index=True),
        sa.Column("branch_name", sa.String(256), nullable=True),
        sa.Column("pr_url", sa.String(512), nullable=True),
        sa.Column("pr_description", sa.Text, nullable=True),
        sa.Column("cost_usd", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("repo_runs")
