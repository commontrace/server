"""Tag trend model.

Tracks per-tag growth rates for emergent pattern detection (stigmergy).
Computed by the consolidation worker, served via GET /api/v1/tags/trending.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class TagTrend(Base):
    __tablename__ = "tag_trends"
    __table_args__ = (
        UniqueConstraint("tag_name", "period_end", name="uq_tag_trends_tag_name_period_end"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tag_name: Mapped[str] = mapped_column(String(50), nullable=False)
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    trace_count_period: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    trace_count_prior: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    growth_rate: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="0.0"
    )
    is_trending: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
