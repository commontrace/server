"""Retrieval tracking and rich encoding columns

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-02-25 00:04:00.000000

Adds 4 columns to traces for neuroscience-inspired memory features:
- retrieval_count: Hebbian strengthening — tracks how often a trace is retrieved
- last_retrieved_at: freshness anchor for temporal decay
- depth_score: encoding richness — traces with more context rank higher
- half_life_days: domain-specific decay rate (frontend decays faster than infra)

Written manually (not via autogenerate) consistent with project migration policy.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "traces",
        sa.Column(
            "retrieval_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "traces",
        sa.Column(
            "last_retrieved_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "traces",
        sa.Column(
            "depth_score",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "traces",
        sa.Column(
            "half_life_days",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_traces_last_retrieved_at",
        "traces",
        ["last_retrieved_at"],
    )
    op.create_index(
        "ix_traces_depth_score",
        "traces",
        ["depth_score"],
    )


def downgrade() -> None:
    op.drop_index("ix_traces_depth_score", table_name="traces")
    op.drop_index("ix_traces_last_retrieved_at", table_name="traces")
    op.drop_column("traces", "half_life_days")
    op.drop_column("traces", "depth_score")
    op.drop_column("traces", "last_retrieved_at")
    op.drop_column("traces", "retrieval_count")
