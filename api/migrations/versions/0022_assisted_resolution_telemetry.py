"""assisted_resolution_telemetry

Revision ID: 220a1b2c3d4e
Revises: 210a1b2c3d4e
Create Date: 2026-06-11 00:00:00.000000

Adds four nullable Integer columns to trigger_stats to capture the
assisted-resolution north-star metric (spec §4.3):
  - searches_fired
  - traces_consumed
  - resolutions_total
  - resolutions_assisted

Nullable so existing rows (skill < 0.5.2) remain valid.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "220a1b2c3d4e"
down_revision = "210a1b2c3d4e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "trigger_stats",
        sa.Column("searches_fired", sa.Integer(), nullable=True),
    )
    op.add_column(
        "trigger_stats",
        sa.Column("traces_consumed", sa.Integer(), nullable=True),
    )
    op.add_column(
        "trigger_stats",
        sa.Column("resolutions_total", sa.Integer(), nullable=True),
    )
    op.add_column(
        "trigger_stats",
        sa.Column("resolutions_assisted", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("trigger_stats", "resolutions_assisted")
    op.drop_column("trigger_stats", "resolutions_total")
    op.drop_column("trigger_stats", "traces_consumed")
    op.drop_column("trigger_stats", "searches_fired")
