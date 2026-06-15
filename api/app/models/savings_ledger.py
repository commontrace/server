import uuid
from datetime import datetime
from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class SavingsLedger(Base):
    __tablename__ = "savings_ledger"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    minutes_saved: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    tokens_saved: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
