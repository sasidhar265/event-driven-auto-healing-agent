import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import EventStatus, SuggestionStatus
from app.runtime_config import get_runtime_rules


class EventCreate(BaseModel):
    external_id: str = Field(min_length=1, max_length=200)
    event_type: str = Field(min_length=1, max_length=150)
    source: str = Field(min_length=1, max_length=200)
    severity: str = Field(pattern="^(info|warning|error|critical)$")
    correlation_key: str = Field(min_length=1, max_length=300)
    payload: dict[str, Any]


class EventRead(EventCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: str
    status: EventStatus
    created_at: datetime
    processed_at: datetime | None


class SuggestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    event_id: uuid.UUID
    correlation_id: str | None = None
    tenant_id: str
    agent_type: str
    title: str
    rationale: str
    proposed_changes: dict[str, Any]
    evidence: list[dict[str, Any]]
    confidence: float
    policy_result: dict[str, Any]
    status: SuggestionStatus
    created_at: datetime


class DecisionCreate(BaseModel):
    decision: str = Field(pattern="^(accepted|rejected)$")
    reason: str = Field(min_length=1, max_length=1000)


class RecoveryEvaluationCreate(BaseModel):
    before: dict[str, float]
    after: dict[str, float]
    observation_seconds: int = Field(default=300, ge=30, le=86400)


class PolicyCreate(BaseModel):
    name: str
    rules: dict[str, Any]


class KnowledgeCreate(BaseModel):
    title: str
    content: str
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CloudEventCreate(BaseModel):
    specversion: str = Field(pattern=r"^1\.0$")
    id: str = Field(min_length=1, max_length=200)
    source: str = Field(min_length=1, max_length=200)
    type: str = Field(default="unclassified.failure", min_length=1, max_length=150)
    subject: str | None = Field(default=None, max_length=300)
    time: datetime | None = None
    dataschema: str | None = None
    datacontenttype: str = "application/json"
    data: dict[str, Any]
    severity: str = Field(default="error", pattern="^(info|warning|error|critical)$")
    correlationid: str | None = Field(default=None, max_length=300)

    @field_validator("type", mode="before")
    @classmethod
    def default_missing_type(cls, value: Any) -> Any:
        """Keep an actionable error when a backbone omits its event type."""
        if value is None or (isinstance(value, str) and not value.strip()):
            return "unclassified.failure"
        return value


class SubscriptionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    callback_url: str = Field(pattern=r"^https?://", max_length=2000)
    event_types: list[str] = Field(
        default_factory=lambda: [get_runtime_rules().delivery.cloud_event_type]
    )
    secret: str | None = Field(default=None, min_length=16, max_length=500)


class SubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: str
    name: str
    callback_url: str
    event_types: list[str]
    active: bool
    created_at: datetime
