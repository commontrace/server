"""Add solution_embedding column to traces

Revision ID: 130b2c3d4e5f
Revises: a1b2c3d4e5f6
Create Date: 2026-02-26 23:01:00.000000

Separate solution vector for multi-vector search (Principle 3 — Dual Coding).
Used in contradiction detection, not in primary search path.
No HNSW index — only used for pairwise comparisons within clusters.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision: str = "130b2c3d4e5f"
down_revision: str = "120a1b2c3d4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "traces",
        sa.Column("solution_embedding", Vector(1536), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("traces", "solution_embedding")
