import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .trace import Trace
    from .vote import Vote


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    api_key_hash: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    reputation_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_seed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_moderator: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    country_code: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    platform: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    skill_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    install_source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Contribution gate (spec §6.4) — publishing requires an invitation.
    # Reading and search stay open; can_contribute gates writes only.
    can_contribute: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="false"
    )
    entry_door: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    invited_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    invites_remaining: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, server_default="0"
    )

    # Relationships
    traces: Mapped[list["Trace"]] = relationship("Trace", back_populates="contributor")
    votes: Mapped[list["Vote"]] = relationship("Vote", back_populates="voter")
