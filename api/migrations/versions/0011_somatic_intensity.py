"""Add somatic_intensity column to traces

Revision ID: f1a2b3c4d5e6
Revises: e1f2a3b4c5d6
Create Date: 2026-02-26 22:00:00.000000

Damasio-inspired intensity marker: persists how intensely knowledge was
learned (error count, time invested, pattern type) as a 0.0-1.0 float
for search ranking amplification.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: str = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "traces",
        sa.Column("somatic_intensity", sa.Float(), nullable=False, server_default="0.0"),
    )


def downgrade() -> None:
    op.drop_column("traces", "somatic_intensity")
