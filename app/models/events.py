"""Incident and remediation-suggestion persistence models."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class EventStatus(str, enum.Enum):
    RECEIVED = "received"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class SuggestionStatus(str, enum.Enum):
    SUPPRESSED = "suppressed"
    REVIEW = "review"
    READY = "ready"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "external_id", name="uq_events_tenant_external"),
        Index("ix_events_tenant_correlation", "tenant_id", "correlation_key"),
        Index("ix_events_status_created", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    external_id: Mapped[str] = mapped_column(String(200))
    event_type: Mapped[str] = mapped_column(String(150))
    source: Mapped[str] = mapped_column(String(200))
    severity: Mapped[str] = mapped_column(String(30))
    correlation_key: Mapped[str] = mapped_column(String(300))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[EventStatus] = mapped_column(Enum(EventStatus), default=EventStatus.RECEIVED)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suggestions: Mapped[list["Suggestion"]] = relationship(back_populates="event")


class Suggestion(Base):
    __tablename__ = "suggestions"
    __table_args__ = (Index("ix_suggestions_tenant_status", "tenant_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id"), index=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    agent_type: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(250))
    rationale: Mapped[str] = mapped_column(Text)
    proposed_changes: Mapped[dict[str, Any]] = mapped_column(JSONB)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    confidence: Mapped[float] = mapped_column(Float)
    policy_result: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[SuggestionStatus] = mapped_column(Enum(SuggestionStatus))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    event: Mapped[Event] = relationship(back_populates="suggestions")
