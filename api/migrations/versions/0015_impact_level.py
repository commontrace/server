"""Add impact_level column to traces

Revision ID: d4e5f6a1b2c3
Revises: c3d4e5f6a1b2
Create Date: 2026-02-26 23:03:00.000000

Categorical importance level (critical/high/normal/low) for Principle 12 —
Emotional Salience. Provides permanent decay floor: critical traces never
fall below 70% of their peak score. Complements continuous somatic_intensity.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "d4e5f6a1b2c3"
down_revision: str = "c3d4e5f6a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "traces",
        sa.Column(
            "impact_level",
            sa.String(10),
            nullable=False,
            server_default="normal",
        ),
    )
    op.create_index("ix_traces_impact_level", "traces", ["impact_level"])


def downgrade() -> None:
    op.drop_index("ix_traces_impact_level", table_name="traces")
    op.drop_column("traces", "impact_level")
