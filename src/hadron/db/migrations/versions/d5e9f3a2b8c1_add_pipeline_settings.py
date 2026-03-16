"""add pipeline_settings table

Revision ID: d5e9f3a2b8c1
Revises: c4d8e2f1a7b9
Create Date: 2026-03-16 14:00:00.000000

"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d5e9f3a2b8c1"
down_revision: Union[str, Sequence[str]] = "c4d8e2f1a7b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SEED_STAGE_MODELS = {
    "intake": {
        "act": {"backend": "claude", "model": "claude-haiku-4-5-20251001"},
        "explore": None,
        "plan": None,
    },
    "behaviour_translation": {
        "act": {"backend": "claude", "model": "claude-sonnet-4-6"},
        "explore": None,
        "plan": None,
    },
    "behaviour_verification": {
        "act": {"backend": "claude", "model": "claude-haiku-4-5-20251001"},
        "explore": None,
        "plan": None,
    },
    "implementation": {
        "act": {"backend": "claude", "model": "claude-sonnet-4-6"},
        "explore": {"backend": "claude", "model": "claude-haiku-4-5-20251001"},
        "plan": {"backend": "claude", "model": "claude-opus-4-6"},
    },
    "review:security_reviewer": {
        "act": {"backend": "claude", "model": "claude-sonnet-4-6"},
        "explore": None,
        "plan": None,
    },
    "review:quality_reviewer": {
        "act": {"backend": "claude", "model": "claude-haiku-4-5-20251001"},
        "explore": None,
        "plan": None,
    },
    "review:spec_compliance_reviewer": {
        "act": {"backend": "claude", "model": "claude-haiku-4-5-20251001"},
        "explore": None,
        "plan": None,
    },
    "rework": {
        "act": {"backend": "claude", "model": "claude-sonnet-4-6"},
        "explore": None,
        "plan": None,
    },
    "rebase": {
        "act": {"backend": "claude", "model": "claude-sonnet-4-6"},
        "explore": None,
        "plan": None,
    },
}


def upgrade() -> None:
    op.create_table(
        "pipeline_settings",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("value_json", sa.JSON, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Seed with defaults
    pipeline_settings = sa.table(
        "pipeline_settings",
        sa.column("key", sa.String),
        sa.column("value_json", sa.JSON),
    )
    op.bulk_insert(
        pipeline_settings,
        [
            {"key": "default_backend", "value_json": json.dumps({"backend": "claude"})},
            {"key": "stage_models", "value_json": json.dumps(_SEED_STAGE_MODELS)},
        ],
    )


def downgrade() -> None:
    op.drop_table("pipeline_settings")
