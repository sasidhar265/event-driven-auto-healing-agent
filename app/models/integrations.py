"""External integration checkpoint models."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class IntegrationPublication(Base):
    __tablename__ = "integration_publications"
    __table_args__ = (
        UniqueConstraint("suggestion_id", "target", name="uq_integration_suggestion_target"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    suggestion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("suggestions.id"), index=True
    )
    target: Mapped[str] = mapped_column(String(500))
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class IntegrationIngestion(Base):
    __tablename__ = "integration_ingestions"
    __table_args__ = (
        UniqueConstraint("event_id", "source", name="uq_integration_event_source"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id"), index=True)
    source: Mapped[str] = mapped_column(String(500))
    external_id: Mapped[str] = mapped_column(String(500))
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
