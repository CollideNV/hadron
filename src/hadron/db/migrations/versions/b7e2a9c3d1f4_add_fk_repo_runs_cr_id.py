"""add foreign key repo_runs.cr_id -> cr_runs.cr_id

Revision ID: b7e2a9c3d1f4
Revises: a3f1c2d4e5b6
Create Date: 2026-03-11 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "b7e2a9c3d1f4"
down_revision: Union[str, Sequence[str], None] = "a3f1c2d4e5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_repo_runs_cr_id",
        "repo_runs",
        "cr_runs",
        ["cr_id"],
        ["cr_id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_repo_runs_cr_id", "repo_runs", type_="foreignkey")
