"""Prospective memory

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-02-25 00:06:00.000000

Adds review_after and watch_condition columns to traces for prospective
memory — scheduled re-validation and conditional staleness triggers.

Written manually (not via autogenerate) consistent with project migration policy.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "traces",
        sa.Column("review_after", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "traces",
        sa.Column("watch_condition", sa.String(500), nullable=True),
    )
    op.create_index(
        "ix_traces_review_after",
        "traces",
        ["review_after"],
    )


def downgrade() -> None:
    op.drop_index("ix_traces_review_after", table_name="traces")
    op.drop_column("traces", "watch_condition")
    op.drop_column("traces", "review_after")
