"""Create savings_ledger table.

Append-only, anonymized savings increments from skill clients (Savings &
Impact system, spec phase 4). Each row: minutes_saved, tokens_saved,
event_type, created_at. NO user, NO trace, NO content — matches the
anonymized-telemetry privacy envelope (docs/privacy-what-is-shared.md).

Revision ID: 230a1b2c3d4e
Revises: 220a1b2c3d4e
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "230a1b2c3d4e"
down_revision: str = "220a1b2c3d4e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "savings_ledger",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("minutes_saved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_saved", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_savings_ledger_created_at", "savings_ledger", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_savings_ledger_created_at", table_name="savings_ledger")
    op.drop_table("savings_ledger")
