"""Add user telemetry fields for install/DAU/geo analytics.

Revision ID: 190a1b2c3d4e
Revises: 180a0b0c0d0e
Create Date: 2026-05-25 12:00:00.000000

Adds last_seen_at, country_code, platform, skill_version, install_source
to users for DAU and acquisition analytics. All fields nullable so the
migration is non-blocking. Indexes on last_seen_at and country_code for
aggregate queries in /api/v1/analytics.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "190a1b2c3d4e"
down_revision: str = "180a0b0c0d0e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("country_code", sa.String(length=2), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("platform", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("skill_version", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("install_source", sa.String(length=50), nullable=True),
    )
    op.create_index("ix_users_last_seen_at", "users", ["last_seen_at"])
    op.create_index("ix_users_country_code", "users", ["country_code"])
    op.create_index("ix_users_created_at", "users", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_users_created_at", table_name="users")
    op.drop_index("ix_users_country_code", table_name="users")
    op.drop_index("ix_users_last_seen_at", table_name="users")
    op.drop_column("users", "install_source")
    op.drop_column("users", "skill_version")
    op.drop_column("users", "platform")
    op.drop_column("users", "country_code")
    op.drop_column("users", "last_seen_at")
