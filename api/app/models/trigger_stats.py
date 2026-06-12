"""Trigger stats model.

Stores anonymized trigger effectiveness stats reported by skill clients
at session end. Used to measure which search triggers lead to actual
trace consumption across all users.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class TriggerStats(Base):
    __tablename__ = "trigger_stats"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    stats_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False
    )
    # Assisted-resolution counters (spec §4.3 north-star).
    # Nullable: skill versions before 0.5.2 don't report them.
    searches_fired: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    traces_consumed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    resolutions_total: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    resolutions_assisted: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
