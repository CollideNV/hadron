"""initial cr_runs and audit_log

Revision ID: 96dd58f6d850
Revises:
Create Date: 2026-02-24 20:55:59.772533

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "96dd58f6d850"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cr_runs",
        sa.Column("cr_id", sa.String(64), primary_key=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending", index=True),
        sa.Column("external_id", sa.String(256), unique=True, nullable=True),
        sa.Column("source", sa.String(32), nullable=False, server_default="api"),
        sa.Column("raw_cr_json", sa.JSON, nullable=True),
        sa.Column("config_snapshot_json", sa.JSON, nullable=True),
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

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("cr_id", sa.String(64), nullable=True, index=True),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("details", sa.JSON, nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("cr_runs")
