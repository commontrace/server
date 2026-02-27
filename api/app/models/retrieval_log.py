"""Retrieval log model.

Records individual retrieval events for co-retrieval detection.
Pruned after 30 days by the consolidation worker.
"""

import uuid
from datetime import datetime

from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class RetrievalLog(Base):
    __tablename__ = "retrieval_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    trace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("traces.id"), nullable=False
    )
    search_session_id: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    result_position: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
