"""Validated API contracts for the enterprise ART lifecycle."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

Environment = Literal["dev", "test", "preprod", "prod"]
Status = Literal[
    "RECEIVED",
    "IN_PROGRESS",
    "SUCCESS",
    "FAILED",
    "REQUIRES_APPROVAL",
    "APPROVED",
    "REJECTED",
    "EXECUTED",
    "CANCELLED",
    "SKIPPED",
]
ApprovalStatus = Literal["NOT_REQUIRED", "PENDING", "APPROVED", "REJECTED", "EXPIRED", "CANCELLED"]


class ArtCreate(BaseModel):
    correlation_id: uuid.UUID
    environment: Environment


class FailureEventCreate(ArtCreate):
    source_event_id: uuid.UUID | None = None
    execution_run_id: str | None = Field(default=None, max_length=150)
    test_id: str | None = Field(default=None, max_length=150)
    request_id: str | None = Field(default=None, max_length=150)
    source_system: str = Field(min_length=1, max_length=150)
    failure_category: Literal[
        "UI",
        "API",
        "FUNCTIONAL",
        "DATA",
        "PERFORMANCE",
        "SECURITY",
        "BATCH",
        "MAINFRAME",
        "INFRA",
        "UNKNOWN",
    ] = "UNKNOWN"
    failure_subtype: str | None = Field(default=None, max_length=150)
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "MEDIUM"
    api_endpoint: str | None = None
    status_code: int | None = Field(default=None, ge=100, le=599)
    error_message: str | None = None
    trace_id: str | None = Field(default=None, max_length=200)
    payload_summary: dict[str, Any] = Field(default_factory=dict)
    payload_ref: str | None = None
    artifact_refs: list[Any] = Field(default_factory=list)
    raw_failure_ref: str | None = None

    @model_validator(mode="after")
    def require_external_payload_reference(self):
        if self.payload_summary and not (
            self.payload_ref or self.raw_failure_ref or self.artifact_refs
        ):
            serialized_size = len(str(self.payload_summary))
            if serialized_size > 16_384:
                raise ValueError(
                    "large failure payloads must be stored externally and supplied as payload_ref"
                )
        return self


class AgentRunCreate(ArtCreate):
    workflow_type: Literal[
        "CHANGE_ANALYSIS",
        "FAILURE_ANALYSIS",
        "IMPACT_ANALYSIS",
        "TEST_SELECTION",
        "EXECUTION_ORCHESTRATION",
        "SELF_MAINTENANCE",
    ]
    trigger_event_type: str | None = Field(default=None, max_length=100)
    source_event_id: uuid.UUID | None = None
    status: Status = "RECEIVED"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    execution_time_ms: int | None = Field(default=None, ge=0)
    input_context_ref: str | None = None
    output_decision_ref: str | None = None
    policy_decision_id: uuid.UUID | None = None
    policy_version: str | None = Field(default=None, max_length=100)
    approval_required: bool = False
    approval_id: uuid.UUID | None = None
    failure_reason: str | None = None
    retry_count: int = Field(default=0, ge=0)
    created_by: str | None = Field(default=None, max_length=150)


class AgentRunStepCreate(ArtCreate):
    agent_run_id: uuid.UUID
    agent_name: str = Field(min_length=1, max_length=150)
    step_name: str = Field(min_length=1, max_length=150)
    step_sequence: int = Field(gt=0)
    status: Status = "RECEIVED"
    confidence_score: float | None = Field(default=None, ge=0, le=1)
    confidence_reason: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    execution_time_ms: int | None = Field(default=None, ge=0)
    input_ref: str | None = None
    output_ref: str | None = None
    error_message: str | None = None
    model_version: str | None = Field(default=None, max_length=100)
    prompt_template_version: str | None = Field(default=None, max_length=100)


class DecisionJournalCreate(ArtCreate):
    agent_run_id: uuid.UUID | None = None
    agent_step_id: uuid.UUID | None = None
    decision_type: Literal[
        "IMPACT_ASSESSMENT",
        "TEST_SELECTION",
        "TEST_SEQUENCING",
        "EXECUTION_INTENT",
        "SELF_HEAL_PROPOSAL",
        "OUTCOME_EVALUATION",
    ]
    decision_summary: str = Field(min_length=1)
    rationale: str | None = None
    inputs_ref: str | None = None
    context_ref: str | None = None
    output_ref: str | None = None
    confidence_score: float | None = Field(default=None, ge=0, le=1)
    confidence_reason: str | None = None
    evidence_refs: list[Any] = Field(default_factory=list)
    policy_decision_id: uuid.UUID | None = None
    policy_version: str | None = Field(default=None, max_length=100)
    model_version: str | None = Field(default=None, max_length=100)
    prompt_template_version: str | None = Field(default=None, max_length=100)


class ImpactAssessmentCreate(ArtCreate):
    agent_run_id: uuid.UUID | None = None
    impact_source: Literal["code", "config", "infra", "data", "failure"]
    source_event_id: uuid.UUID | None = None
    component_id: str | None = Field(default=None, max_length=150)
    component_name: str = Field(min_length=1, max_length=250)
    component_type: str | None = Field(default=None, max_length=100)
    service_name: str | None = Field(default=None, max_length=250)
    business_capability_id: str | None = Field(default=None, max_length=150)
    business_capability_name: str | None = Field(default=None, max_length=250)
    impact_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    risk_score: float | None = Field(default=None, ge=0, le=1)
    confidence_score: float | None = Field(default=None, ge=0, le=1)
    description: str | None = None
    affected_test_tags: list[Any] = Field(default_factory=list)
    evidence_refs: list[Any] = Field(default_factory=list)
    knowledge_graph_ref: str | None = None


class ImpactDependencyCreate(ArtCreate):
    impact_assessment_id: uuid.UUID
    dependent_component_id: str | None = Field(default=None, max_length=150)
    dependent_component_name: str = Field(min_length=1, max_length=250)
    dependency_direction: Literal["UPSTREAM", "DOWNSTREAM", "LATERAL", "UNKNOWN"]
    dependency_type: str | None = Field(default=None, max_length=100)
    dependency_confidence: float | None = Field(default=None, ge=0, le=1)
    source_of_dependency: str | None = Field(default=None, max_length=100)
    knowledge_graph_ref: str | None = None
    description: str | None = None


class TestSelectionCreate(ArtCreate):
    agent_run_id: uuid.UUID | None = None
    selection_strategy: str = Field(min_length=1, max_length=100)
    risk_score: float | None = Field(default=None, ge=0, le=1)
    confidence_score: float | None = Field(default=None, ge=0, le=1)
    selected_tests: list[Any]
    skipped_tests: list[Any] = Field(default_factory=list)
    mandatory_tests: list[Any] = Field(default_factory=list)
    affected_components: list[Any] = Field(default_factory=list)
    affected_capabilities: list[Any] = Field(default_factory=list)
    risk_coverage: float | None = Field(default=None, ge=0, le=1)
    estimated_duration_ms: int | None = Field(default=None, ge=0)
    rationale: str | None = None
    evidence_refs: list[Any] = Field(default_factory=list)
    policy_decision_id: uuid.UUID | None = None
    policy_version: str | None = Field(default=None, max_length=100)


class ExecutionIntentCreate(ArtCreate):
    agent_run_id: uuid.UUID | None = None
    test_selection_decision_id: uuid.UUID | None = None
    execution_target: str = Field(min_length=1, max_length=150)
    execution_mode: str = Field(default="ORCHESTRATED", max_length=100)
    selected_tests: list[Any]
    sequence_plan: list[Any] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    status: Status = "RECEIVED"
    policy_decision_id: uuid.UUID | None = None
    policy_version: str | None = Field(default=None, max_length=100)
    approval_required: bool = False
    approval_id: uuid.UUID | None = None
    approval_status: ApprovalStatus = "NOT_REQUIRED"
    external_run_id: str | None = Field(default=None, max_length=150)
    execution_result_ref: str | None = None
    evidence_requirements: list[Any] = Field(default_factory=list)
    evidence_refs: list[Any] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_governance_for_dispatchable_intent(self):
        if self.approval_required and self.approval_status == "NOT_REQUIRED":
            raise ValueError("approval_required intents must use PENDING approval_status")
        if self.status in {"APPROVED", "EXECUTED"} and not self.policy_decision_id:
            raise ValueError("approved or executed intents require policy_decision_id")
        return self


class ExecutionResultCreate(ArtCreate):
    execution_intent_id: uuid.UUID | None = None
    external_run_id: str | None = Field(default=None, max_length=150)
    status: Status
    passed_count: int | None = Field(default=None, ge=0)
    failed_count: int | None = Field(default=None, ge=0)
    skipped_count: int | None = Field(default=None, ge=0)
    failures_summary: list[Any] = Field(default_factory=list)
    artifact_refs: list[Any] = Field(default_factory=list)
    result_ref: str | None = None


class SelfHealProposalCreate(ArtCreate):
    agent_run_id: uuid.UUID | None = None
    failure_event_id: uuid.UUID | None = None
    proposal_type: Literal["LOCATOR", "TEST_DATA", "ASSERTION", "MINOR_LOGIC", "CONFIG_DEPENDENCY"]
    proposal_summary: str = Field(min_length=1)
    suggested_change: dict[str, Any]
    proposed_diff: dict[str, Any] = Field(default_factory=dict)
    confidence_score: float | None = Field(default=None, ge=0, le=1)
    confidence_reason: str | None = None
    approval_required: bool = True
    approval_id: uuid.UUID | None = None
    approval_status: ApprovalStatus = "PENDING"
    applied_status: Status = "RECEIVED"
    applied_at: datetime | None = None
    applied_by: str | None = Field(default=None, max_length=150)
    rollback_ref: str | None = None
    evidence_refs: list[Any] = Field(default_factory=list)
    policy_decision_id: uuid.UUID | None = None
    policy_version: str | None = Field(default=None, max_length=100)


class OutcomeFeedbackCreate(ArtCreate):
    agent_run_id: uuid.UUID | None = None
    execution_intent_id: uuid.UUID | None = None
    execution_result_ref_id: uuid.UUID | None = None
    feedback_type: str = Field(min_length=1, max_length=100)
    feedback_summary: str | None = None
    test_effectiveness: dict[str, Any] = Field(default_factory=dict)
    flakiness_signals: dict[str, Any] = Field(default_factory=dict)
    defect_detection_signals: dict[str, Any] = Field(default_factory=dict)
    model_drift_signals: dict[str, Any] = Field(default_factory=dict)
    recommended_action: str | None = None
    published_to_kai: bool = False
    published_at: datetime | None = None


class EventInboxCreate(ArtCreate):
    event_id: uuid.UUID
    topic_name: str = Field(min_length=1, max_length=150)
    event_type: str = Field(min_length=1, max_length=100)
    payload: dict[str, Any]
    processing_status: Status = "RECEIVED"
    processed_at: datetime | None = None
    error_message: str | None = None


class EventOutboxCreate(ArtCreate):
    topic_name: str = Field(min_length=1, max_length=150)
    event_type: str = Field(min_length=1, max_length=100)
    payload: dict[str, Any]
    publish_status: Status = "RECEIVED"
    published_at: datetime | None = None
    error_message: str | None = None


class LifecycleStateUpdate(BaseModel):
    status: Status
    policy_decision_id: uuid.UUID | None = None
    policy_version: str | None = Field(default=None, max_length=100)
    approval_id: uuid.UUID | None = None
    approval_status: ApprovalStatus | None = None
    external_run_id: str | None = Field(default=None, max_length=150)
    failure_reason: str | None = None


class ArtResourceResponse(BaseModel):
    resource_id: uuid.UUID
    correlation_id: uuid.UUID
    tenant_id: str
    environment: Environment
    status: str
    created_at: datetime
    updated_at: datetime | None = None
    data: dict[str, Any]
