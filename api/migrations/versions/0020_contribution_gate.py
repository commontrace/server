"""Contribution gate: invitations table + user gate fields (spec §6.4).

Revision ID: 200a1b2c3d4e
Revises: 190a1b2c3d4e
Create Date: 2026-06-11 12:00:00.000000

Adds can_contribute / entry_door / invited_by / invites_remaining to users,
creates the invitations table, and backfills existing contributors (seed
users, moderators, anyone who has already submitted a trace) as founding
contributors with 2 invites — the gate must never lock out the people who
built the current corpus.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "200a1b2c3d4e"
down_revision: str = "190a1b2c3d4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "can_contribute",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "users",
        sa.Column("entry_door", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "invited_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "invites_remaining",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    op.create_table(
        "invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code_hash", sa.String(length=255), nullable=False, unique=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "redeemed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "door", sa.String(length=16), nullable=False, server_default="vouched"
        ),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_invitations_created_by", "invitations", ["created_by"])

    # Founding backfill — existing contributors keep publishing rights.
    op.execute(
        "UPDATE users SET can_contribute = true, entry_door = 'founding', "
        "invites_remaining = 2 "
        "WHERE is_seed = true OR is_moderator = true OR id IN "
        "(SELECT DISTINCT contributor_id FROM traces WHERE contributor_id IS NOT NULL)"
    )


def downgrade() -> None:
    op.drop_index("ix_invitations_created_by", table_name="invitations")
    op.drop_table("invitations")
    op.drop_column("users", "invites_remaining")
    op.drop_column("users", "invited_by")
    op.drop_column("users", "entry_door")
    op.drop_column("users", "can_contribute")
