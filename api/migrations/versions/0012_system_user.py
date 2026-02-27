"""Seed system user for pattern trace generation

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-02-26 23:00:00.000000

The system user (00000000-0000-0000-0000-000000000001) is the contributor
for auto-generated pattern traces from convergence clusters.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO users (id, api_key_hash, email, created_at) "
        "VALUES ('00000000-0000-0000-0000-000000000001', 'SYSTEM', "
        "'system@commontrace.org', now()) "
        "ON CONFLICT (id) DO NOTHING"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM users WHERE id = '00000000-0000-0000-0000-000000000001'"
    )
