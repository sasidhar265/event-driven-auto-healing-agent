"""Enterprise ART lifecycle records described by the ART feedback specification."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class ArtStatus(str, enum.Enum):
    RECEIVED = "RECEIVED"
    IN_PROGRESS = "IN_PROGRESS"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"


class ArtRecord:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    correlation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    environment: Mapped[str] = mapped_column(String(20), index=True)


class TimestampedRecord:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FailureEvent(ArtRecord, TimestampedRecord, Base):
    __tablename__ = "failure_events"
    __table_args__ = {"schema": "art"}

    source_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    execution_run_id: Mapped[str | None] = mapped_column(String(150))
    test_id: Mapped[str | None] = mapped_column(String(150))
    request_id: Mapped[str | None] = mapped_column(String(150))
    source_system: Mapped[str] = mapped_column(String(150))
    failure_category: Mapped[str] = mapped_column(String(30), default="UNKNOWN")
    failure_subtype: Mapped[str | None] = mapped_column(String(150))
    severity: Mapped[str] = mapped_column(String(20), default="MEDIUM")
    api_endpoint: Mapped[str | None] = mapped_column(Text)
    status_code: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    trace_id: Mapped[str | None] = mapped_column(String(200))
    payload_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    payload_ref: Mapped[str | None] = mapped_column(Text)
    artifact_refs: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    raw_failure_ref: Mapped[str | None] = mapped_column(Text)


class AgentRun(ArtRecord, TimestampedRecord, Base):
    __tablename__ = "agent_runs"
    __table_args__ = {"schema": "art"}

    workflow_type: Mapped[str] = mapped_column(String(50))
    trigger_event_type: Mapped[str | None] = mapped_column(String(100))
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(30), default=ArtStatus.RECEIVED.value)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execution_time_ms: Mapped[int | None] = mapped_column(Integer)
    input_context_ref: Mapped[str | None] = mapped_column(Text)
    output_decision_ref: Mapped[str | None] = mapped_column(Text)
    policy_decision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    policy_version: Mapped[str | None] = mapped_column(String(100))
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False)
    approval_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str | None] = mapped_column(String(150))


class AgentRunStep(ArtRecord, TimestampedRecord, Base):
    __tablename__ = "agent_run_steps"
    __table_args__ = {"schema": "art"}

    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("art.agent_runs.id", ondelete="CASCADE"), index=True
    )
    agent_name: Mapped[str] = mapped_column(String(150))
    step_name: Mapped[str] = mapped_column(String(150))
    step_sequence: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default=ArtStatus.RECEIVED.value)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    confidence_reason: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execution_time_ms: Mapped[int | None] = mapped_column(Integer)
    input_ref: Mapped[str | None] = mapped_column(Text)
    output_ref: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    model_version: Mapped[str | None] = mapped_column(String(100))
    prompt_template_version: Mapped[str | None] = mapped_column(String(100))


class AgentDecisionJournal(ArtRecord, Base):
    __tablename__ = "agent_decision_journals"
    __table_args__ = {"schema": "art"}

    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("art.agent_runs.id", ondelete="SET NULL")
    )
    agent_step_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("art.agent_run_steps.id", ondelete="SET NULL")
    )
    decision_type: Mapped[str] = mapped_column(String(50))
    decision_summary: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str | None] = mapped_column(Text)
    inputs_ref: Mapped[str | None] = mapped_column(Text)
    context_ref: Mapped[str | None] = mapped_column(Text)
    output_ref: Mapped[str | None] = mapped_column(Text)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    confidence_reason: Mapped[str | None] = mapped_column(Text)
    evidence_refs: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    policy_decision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    policy_version: Mapped[str | None] = mapped_column(String(100))
    model_version: Mapped[str | None] = mapped_column(String(100))
    prompt_template_version: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ImpactAssessment(ArtRecord, Base):
    __tablename__ = "impact_assessments"
    __table_args__ = {"schema": "art"}

    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("art.agent_runs.id", ondelete="SET NULL")
    )
    impact_source: Mapped[str] = mapped_column(String(30))
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    component_id: Mapped[str | None] = mapped_column(String(150))
    component_name: Mapped[str] = mapped_column(String(250))
    component_type: Mapped[str | None] = mapped_column(String(100))
    service_name: Mapped[str | None] = mapped_column(String(250))
    business_capability_id: Mapped[str | None] = mapped_column(String(150))
    business_capability_name: Mapped[str | None] = mapped_column(String(250))
    impact_level: Mapped[str] = mapped_column(String(20))
    risk_score: Mapped[float | None] = mapped_column(Float)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    description: Mapped[str | None] = mapped_column(Text)
    affected_test_tags: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    evidence_refs: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    knowledge_graph_ref: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ImpactDependency(ArtRecord, Base):
    __tablename__ = "impact_dependencies"
    __table_args__ = {"schema": "art"}

    impact_assessment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("art.impact_assessments.id", ondelete="CASCADE")
    )
    dependent_component_id: Mapped[str | None] = mapped_column(String(150))
    dependent_component_name: Mapped[str] = mapped_column(String(250))
    dependency_direction: Mapped[str] = mapped_column(String(50))
    dependency_type: Mapped[str | None] = mapped_column(String(100))
    dependency_confidence: Mapped[float | None] = mapped_column(Float)
    source_of_dependency: Mapped[str | None] = mapped_column(String(100))
    knowledge_graph_ref: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TestSelectionDecision(ArtRecord, Base):
    __tablename__ = "test_selection_decisions"
    __table_args__ = {"schema": "art"}

    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("art.agent_runs.id", ondelete="SET NULL")
    )
    selection_strategy: Mapped[str] = mapped_column(String(100))
    risk_score: Mapped[float | None] = mapped_column(Float)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    selected_tests: Mapped[list[Any]] = mapped_column(JSONB)
    skipped_tests: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    mandatory_tests: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    affected_components: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    affected_capabilities: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    risk_coverage: Mapped[float | None] = mapped_column(Float)
    estimated_duration_ms: Mapped[int | None] = mapped_column(Integer)
    rationale: Mapped[str | None] = mapped_column(Text)
    evidence_refs: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    policy_decision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    policy_version: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExecutionIntent(ArtRecord, TimestampedRecord, Base):
    __tablename__ = "execution_intents"
    __table_args__ = {"schema": "art"}

    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("art.agent_runs.id", ondelete="SET NULL")
    )
    test_selection_decision_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("art.test_selection_decisions.id", ondelete="SET NULL")
    )
    execution_target: Mapped[str] = mapped_column(String(150))
    execution_mode: Mapped[str] = mapped_column(String(100), default="ORCHESTRATED")
    selected_tests: Mapped[list[Any]] = mapped_column(JSONB)
    sequence_plan: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    constraints: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(30), default=ArtStatus.RECEIVED.value)
    policy_decision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    policy_version: Mapped[str | None] = mapped_column(String(100))
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False)
    approval_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approval_status: Mapped[str] = mapped_column(String(30), default="NOT_REQUIRED")
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    external_run_id: Mapped[str | None] = mapped_column(String(150))
    execution_result_ref: Mapped[str | None] = mapped_column(Text)
    evidence_requirements: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    evidence_refs: Mapped[list[Any]] = mapped_column(JSONB, default=list)


class ExecutionResultRef(ArtRecord, Base):
    __tablename__ = "execution_result_refs"
    __table_args__ = {"schema": "art"}

    execution_intent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("art.execution_intents.id", ondelete="SET NULL")
    )
    external_run_id: Mapped[str | None] = mapped_column(String(150))
    status: Mapped[str] = mapped_column(String(30))
    passed_count: Mapped[int | None] = mapped_column(Integer)
    failed_count: Mapped[int | None] = mapped_column(Integer)
    skipped_count: Mapped[int | None] = mapped_column(Integer)
    failures_summary: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    artifact_refs: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    result_ref: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SelfHealProposal(ArtRecord, TimestampedRecord, Base):
    __tablename__ = "self_heal_proposals"
    __table_args__ = {"schema": "art"}

    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("art.agent_runs.id", ondelete="SET NULL")
    )
    failure_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("art.failure_events.id", ondelete="SET NULL")
    )
    proposal_type: Mapped[str] = mapped_column(String(50))
    proposal_summary: Mapped[str] = mapped_column(Text)
    suggested_change: Mapped[dict[str, Any]] = mapped_column(JSONB)
    proposed_diff: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    confidence_reason: Mapped[str | None] = mapped_column(Text)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=True)
    approval_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approval_status: Mapped[str] = mapped_column(String(30), default="PENDING")
    applied_status: Mapped[str] = mapped_column(String(30), default=ArtStatus.RECEIVED.value)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_by: Mapped[str | None] = mapped_column(String(150))
    rollback_ref: Mapped[str | None] = mapped_column(Text)
    evidence_refs: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    policy_decision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    policy_version: Mapped[str | None] = mapped_column(String(100))


class OutcomeFeedback(ArtRecord, Base):
    __tablename__ = "outcome_feedback"
    __table_args__ = {"schema": "art"}

    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("art.agent_runs.id", ondelete="SET NULL")
    )
    execution_intent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("art.execution_intents.id", ondelete="SET NULL")
    )
    execution_result_ref_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("art.execution_result_refs.id", ondelete="SET NULL")
    )
    feedback_type: Mapped[str] = mapped_column(String(100))
    feedback_summary: Mapped[str | None] = mapped_column(Text)
    test_effectiveness: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    flakiness_signals: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    defect_detection_signals: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    model_drift_signals: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    recommended_action: Mapped[str | None] = mapped_column(Text)
    published_to_kai: Mapped[bool] = mapped_column(Boolean, default=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ArtEventInbox(ArtRecord, Base):
    __tablename__ = "event_inbox"
    __table_args__ = {"schema": "art"}

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    topic_name: Mapped[str] = mapped_column(String(150))
    event_type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    processing_status: Mapped[str] = mapped_column(String(30), default=ArtStatus.RECEIVED.value)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)


class ArtEventOutbox(ArtRecord, Base):
    __tablename__ = "event_outbox"
    __table_args__ = {"schema": "art"}

    topic_name: Mapped[str] = mapped_column(String(150))
    event_type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    publish_status: Mapped[str] = mapped_column(String(30), default=ArtStatus.RECEIVED.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
