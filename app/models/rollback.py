from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RollbackRecord(Base):
    __tablename__ = "rollback_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # What was done
    action_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    module: Mapped[str] = mapped_column(String(64), nullable=False)

    # The forward action that was taken
    forward_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Inverse operation to undo it
    inverse_action: Mapped[str] = mapped_column(String(128), nullable=False)
    inverse_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Rollback state
    rolled_back: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    rolled_back_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rollback_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
