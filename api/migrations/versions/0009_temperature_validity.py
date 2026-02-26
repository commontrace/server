"""Temperature and validity

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-02-26 00:09:00.000000

Adds memory_temperature (graduated staleness), valid_from and valid_until
(bi-temporal validity periods) to traces. Backfills existing rows.

Inspired by DroidClaw's temperature classification and bi-temporal model.

Written manually (not via autogenerate) consistent with project migration policy.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Feature 1: Memory Temperature
    op.add_column(
        "traces",
        sa.Column("memory_temperature", sa.String(10), nullable=True),
    )
    op.create_index(
        "ix_traces_memory_temperature",
        "traces",
        ["memory_temperature"],
    )

    # Feature 3: Bi-temporal Validity
    op.add_column(
        "traces",
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "traces",
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_traces_valid_until",
        "traces",
        ["valid_until"],
    )

    # Backfill: valid_from = created_at for existing traces
    op.execute("UPDATE traces SET valid_from = created_at WHERE valid_from IS NULL")

    # Backfill: all existing traces start as WARM; consolidation worker reclassifies
    op.execute("UPDATE traces SET memory_temperature = 'WARM' WHERE memory_temperature IS NULL")


def downgrade() -> None:
    op.drop_index("ix_traces_valid_until", table_name="traces")
    op.drop_index("ix_traces_memory_temperature", table_name="traces")
    op.drop_column("traces", "valid_until")
    op.drop_column("traces", "valid_from")
    op.drop_column("traces", "memory_temperature")
