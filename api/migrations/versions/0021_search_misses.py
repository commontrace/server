"""Create search_misses table.

Records zero-result searches as Wanted Board demand signals (spec §6.3).

Revision ID: 210a1b2c3d4e
Revises: 200a1b2c3d4e
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "210a1b2c3d4e"
down_revision: str = "200a1b2c3d4e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "search_misses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("query_text", sa.String(2000), nullable=True),
        sa.Column("tags", sa.String(500), nullable=True),
        sa.Column("language", sa.String(50), nullable=True),
        sa.Column("framework", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_search_misses_created_at", "search_misses", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_search_misses_created_at", table_name="search_misses")
    op.drop_table("search_misses")
