"""Trace relationship model.

Captures typed relationships between traces: co-retrieval patterns,
supersession chains, complementary knowledge, and pattern sources.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class RelationshipType(str, enum.Enum):
    CO_RETRIEVED = "CO_RETRIEVED"
    SUPERSEDES = "SUPERSEDES"
    COMPLEMENTS = "COMPLEMENTS"
    PATTERN_SOURCE = "PATTERN_SOURCE"


class TraceRelationship(Base):
    __tablename__ = "trace_relationships"
    __table_args__ = (
        UniqueConstraint(
            "source_trace_id", "target_trace_id", "relationship_type",
            name="uq_trace_relationships_source_target_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_trace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("traces.id"), nullable=False
    )
    target_trace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("traces.id"), nullable=False
    )
    relationship_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )
    strength: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="1.0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
