"""RIF shadow model.

Tracks retrieval-induced forgetting: when a trace consistently loses
to the same competitor in search results. Used to detect traces that
are being suppressed by stronger alternatives.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class RifShadow(Base):
    __tablename__ = "rif_shadows"
    __table_args__ = (
        UniqueConstraint("loser_trace_id", "winner_trace_id", name="uq_rif_shadows_loser_winner"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    loser_trace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("traces.id"), nullable=False
    )
    winner_trace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("traces.id"), nullable=False
    )
    loss_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )
    last_observed: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
