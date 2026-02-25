"""Relationships and consolidation

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-02-25 00:05:00.000000

Creates trace_relationships, retrieval_logs, and consolidation_runs tables.
Adds trace_type column to traces for episodic/pattern distinction.

Written manually (not via autogenerate) consistent with project migration policy.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # trace_relationships table
    op.create_table(
        "trace_relationships",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_trace_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("traces.id"),
            nullable=False,
        ),
        sa.Column(
            "target_trace_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("traces.id"),
            nullable=False,
        ),
        sa.Column("relationship_type", sa.String(30), nullable=False),
        sa.Column("strength", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "source_trace_id",
            "target_trace_id",
            "relationship_type",
            name="uq_trace_relationships_source_target_type",
        ),
    )
    op.create_index(
        "ix_trace_relationships_source",
        "trace_relationships",
        ["source_trace_id"],
    )
    op.create_index(
        "ix_trace_relationships_target",
        "trace_relationships",
        ["target_trace_id"],
    )

    # retrieval_logs table
    op.create_table(
        "retrieval_logs",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "trace_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("traces.id"),
            nullable=False,
        ),
        sa.Column("search_session_id", sa.String(100), nullable=False),
        sa.Column(
            "retrieved_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_retrieval_logs_session",
        "retrieval_logs",
        ["search_session_id"],
    )
    op.create_index(
        "ix_retrieval_logs_retrieved_at",
        "retrieval_logs",
        ["retrieved_at"],
    )

    # consolidation_runs table
    op.create_table(
        "consolidation_runs",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="'running'"),
        sa.Column("stats_json", sa.dialects.postgresql.JSON(), nullable=True),
    )

    # Add trace_type to traces
    op.add_column(
        "traces",
        sa.Column(
            "trace_type",
            sa.String(20),
            nullable=False,
            server_default="episodic",
        ),
    )


def downgrade() -> None:
    op.drop_column("traces", "trace_type")
    op.drop_table("consolidation_runs")
    op.drop_index("ix_retrieval_logs_retrieved_at", table_name="retrieval_logs")
    op.drop_index("ix_retrieval_logs_session", table_name="retrieval_logs")
    op.drop_table("retrieval_logs")
    op.drop_index("ix_trace_relationships_target", table_name="trace_relationships")
    op.drop_index("ix_trace_relationships_source", table_name="trace_relationships")
    op.drop_table("trace_relationships")
