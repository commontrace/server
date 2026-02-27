"""Add tag_trends table for stigmergic signal detection

Revision ID: e5f6a1b2c3d4
Revises: d4e5f6a1b2c3
Create Date: 2026-02-26 23:04:00.000000

Tracks fastest-growing tag areas for emergent pattern detection
(Principle 10 — Stigmergy). The consolidation worker computes
7-day growth rates per tag and flags trending topics.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "e5f6a1b2c3d4"
down_revision: str = "d4e5f6a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tag_trends",
        sa.Column("id", sa.dialects.postgresql.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tag_name", sa.String(50), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trace_count_period", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trace_count_prior", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("growth_rate", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("is_trending", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tag_name", "period_end", name="uq_tag_trends_tag_name_period_end"),
    )
    op.create_index(
        "ix_tag_trends_trending",
        "tag_trends",
        ["is_trending", "period_end"],
    )


def downgrade() -> None:
    op.drop_index("ix_tag_trends_trending", table_name="tag_trends")
    op.drop_table("tag_trends")
