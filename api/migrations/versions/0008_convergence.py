"""Convergence detection

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-02-26 00:08:00.000000

Adds convergence_level and convergence_cluster_id to traces for detecting
when different contexts converge on the same solution — promoting repeated
patterns into universal knowledge.

Written manually (not via autogenerate) consistent with project migration policy.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "traces",
        sa.Column("convergence_level", sa.Integer(), nullable=True),
    )
    op.add_column(
        "traces",
        sa.Column("convergence_cluster_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_traces_convergence_cluster_id",
        "traces",
        ["convergence_cluster_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_traces_convergence_cluster_id", table_name="traces")
    op.drop_column("traces", "convergence_cluster_id")
    op.drop_column("traces", "convergence_level")
