"""Add is_moderator flag to users table

Revision ID: f6a1b2c3d4e5
Revises: e5f6a1b2c3d4
Create Date: 2026-03-01 22:00:00.000000

Gates moderation endpoints (list flagged, remove trace) behind
a moderator role check. Prevents any authenticated user from
deleting traces. Addresses CRITICAL finding C1 from security audit.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "f6a1b2c3d4e5"
down_revision: str = "e5f6a1b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_moderator", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("users", "is_moderator")
