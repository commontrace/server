"""Context fields

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-02-26 00:07:00.000000

Adds context_fingerprint (JSON) and context_embedding (Vector) to traces
for contextual knowledge convergence — storing structured environment context
and a dedicated context vector for context-aware search boosting.

Written manually (not via autogenerate) consistent with project migration policy.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "traces",
        sa.Column("context_fingerprint", sa.JSON(), nullable=True),
    )
    op.add_column(
        "traces",
        sa.Column("context_embedding", Vector(1536), nullable=True),
    )
    op.create_index(
        "ix_traces_context_embedding_hnsw",
        "traces",
        ["context_embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"context_embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_traces_context_embedding_hnsw", table_name="traces")
    op.drop_column("traces", "context_embedding")
    op.drop_column("traces", "context_fingerprint")
