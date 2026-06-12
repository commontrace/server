"""Search miss model.

Records zero-result searches — the demand signal for the Wanted Board
(spec §6.3). Aggregate-shape only: the query the agent already sent,
its tags, and coarse context labels (language/framework). Never code,
paths, or repo names.
"""

import uuid
from datetime import datetime

from typing import Optional

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SearchMiss(Base):
    __tablename__ = "search_misses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    query_text: Mapped[Optional[str]] = mapped_column(
        String(2000), nullable=True
    )
    tags: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    language: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )
    framework: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
