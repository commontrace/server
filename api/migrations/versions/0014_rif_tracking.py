"""Add retrieval-induced forgetting tracking

Revision ID: c3d4e5f6a1b2
Revises: b2c3d4e5f6a1
Create Date: 2026-02-26 23:02:00.000000

Tracks which traces consistently lose to the same competitor in search
results (Principle 6 — Retrieval-Induced Forgetting). Adds result_position
to retrieval_logs and creates rif_shadows table.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "c3d4e5f6a1b2"
down_revision: str = "b2c3d4e5f6a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add position tracking to retrieval logs
    op.add_column(
        "retrieval_logs",
        sa.Column("result_position", sa.Integer(), nullable=True),
    )

    # Create RIF shadows table
    op.execute(
        """
        CREATE TABLE rif_shadows (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            loser_trace_id UUID NOT NULL REFERENCES traces(id),
            winner_trace_id UUID NOT NULL REFERENCES traces(id),
            loss_count INTEGER NOT NULL DEFAULT 1,
            last_observed TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(loser_trace_id, winner_trace_id)
        )
        """
    )
    op.create_index("ix_rif_shadows_loser", "rif_shadows", ["loser_trace_id"])


def downgrade() -> None:
    op.drop_index("ix_rif_shadows_loser", table_name="rif_shadows")
    op.drop_table("rif_shadows")
    op.drop_column("retrieval_logs", "result_position")
