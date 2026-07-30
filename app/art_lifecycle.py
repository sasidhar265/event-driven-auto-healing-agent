"""Record the existing remediation pipeline in the enterprise ART lifecycle."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.art_models import (
    AgentDecisionJournal,
    AgentRun,
    AgentRunStep,
    ArtStatus,
    FailureEvent,
    SelfHealProposal,
)
from app.models import Event, Suggestion
from app.services import Candidate, FailureRoute

ENVIRONMENTS = {"dev", "test", "preprod", "prod"}
SEVERITY = {
    "info": "LOW",
    "warning": "MEDIUM",
    "error": "HIGH",
    "critical": "CRITICAL",
}
CATEGORY = {
    "ui": "UI",
    "api": "API",
    "logic": "FUNCTIONAL",
    "functional": "FUNCTIONAL",
    "test_data": "DATA",
    "database": "DATA",
    "infrastructure": "INFRA",
    "dependency": "INFRA",
    "security": "SECURITY",
    "performance": "PERFORMANCE",
}
SELF_HEAL_TYPE = {
    "ui": "LOCATOR",
    "test_data": "TEST_DATA",
    "logic": "MINOR_LOGIC",
    "functional": "ASSERTION",
}


def correlation_uuid(event: Event) -> uuid.UUID:
    """Preserve UUID correlation values and deterministically map legacy strings."""

    try:
        return uuid.UUID(event.correlation_key)
    except (ValueError, TypeError, AttributeError):
        return uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"art:{event.tenant_id}:{event.correlation_key}",
        )


def event_environment(event: Event) -> str:
    value = str(event.payload.get("environment", "dev")).lower()
    return value if value in ENVIRONMENTS else "dev"


class LifecycleRecorder:
    def __init__(self, session: AsyncSession, event: Event):
        self.session = session
        self.event = event
        self.correlation_id = correlation_uuid(event)
        self.environment = event_environment(event)
        self.run: AgentRun | None = None
        self.failure: FailureEvent | None = None
        self.step_sequence = 0

    async def start(self, route: FailureRoute) -> None:
        payload = self.event.payload
        self.failure = FailureEvent(
            correlation_id=self.correlation_id,
            tenant_id=self.event.tenant_id,
            environment=self.environment,
            source_event_id=self.event.id,
            execution_run_id=payload.get("execution_run_id"),
            test_id=payload.get("test_id") or payload.get("test_name"),
            request_id=payload.get("request_id"),
            source_system=self.event.source,
            failure_category=CATEGORY.get(route.category, "UNKNOWN"),
            failure_subtype=self.event.event_type,
            severity=SEVERITY.get(self.event.severity.lower(), "MEDIUM"),
            api_endpoint=payload.get("endpoint"),
            status_code=payload.get("status_code"),
            error_message=payload.get("error") or payload.get("message"),
            trace_id=payload.get("trace_id"),
            payload_summary=self._safe_payload_summary(payload),
            payload_ref=payload.get("payload_ref"),
            artifact_refs=payload.get("artifact_refs", []),
            raw_failure_ref=payload.get("raw_failure_ref"),
        )
        self.run = AgentRun(
            correlation_id=self.correlation_id,
            tenant_id=self.event.tenant_id,
            environment=self.environment,
            workflow_type="FAILURE_ANALYSIS",
            trigger_event_type=self.event.event_type,
            source_event_id=self.event.id,
            status=ArtStatus.IN_PROGRESS.value,
            started_at=datetime.now(UTC),
            input_context_ref=payload.get("context_ref"),
            created_by="event-runtime",
        )
        self.session.add_all([self.failure, self.run])
        await self.session.flush()
        await self.record_step(
            agent_name="failure-router",
            step_name="classify_failure",
            status=ArtStatus.SUCCESS.value,
            confidence=route.confidence,
            confidence_reason=", ".join(route.matched_signals),
        )

    async def record_candidate(
        self,
        candidate: Candidate,
        suggestion: Suggestion,
    ) -> None:
        if self.run is None:
            return
        step = await self.record_step(
            agent_name=candidate.agent_type,
            step_name="generate_remediation",
            status=ArtStatus.SUCCESS.value,
            confidence=suggestion.confidence,
            confidence_reason=candidate.rationale,
            output_ref=f"suggestion:{suggestion.id}",
        )
        self.session.add(
            AgentDecisionJournal(
                correlation_id=self.correlation_id,
                tenant_id=self.event.tenant_id,
                environment=self.environment,
                agent_run_id=self.run.id,
                agent_step_id=step.id,
                decision_type="SELF_HEAL_PROPOSAL",
                decision_summary=candidate.title,
                rationale=candidate.rationale,
                output_ref=f"suggestion:{suggestion.id}",
                confidence_score=suggestion.confidence,
                confidence_reason=candidate.rationale,
                evidence_refs=suggestion.evidence,
                policy_version=str(suggestion.policy_result.get("policies", "")),
                model_version="deterministic-or-enterprise-gateway",
            )
        )
        proposal_type = SELF_HEAL_TYPE.get(candidate.agent_type)
        if proposal_type:
            self.session.add(
                SelfHealProposal(
                    correlation_id=self.correlation_id,
                    tenant_id=self.event.tenant_id,
                    environment=self.environment,
                    agent_run_id=self.run.id,
                    failure_event_id=self.failure.id if self.failure else None,
                    proposal_type=proposal_type,
                    proposal_summary=candidate.title,
                    suggested_change=candidate.proposed_changes,
                    confidence_score=suggestion.confidence,
                    confidence_reason=candidate.rationale,
                    approval_required=True,
                    approval_status="PENDING",
                    applied_status=ArtStatus.REQUIRES_APPROVAL.value,
                    rollback_ref=candidate.proposed_changes.get("rollback"),
                    evidence_refs=suggestion.evidence,
                )
            )

    async def complete(self, *, failed: bool = False, reason: str | None = None) -> None:
        if self.run is None:
            return
        completed_at = datetime.now(UTC)
        self.run.status = ArtStatus.FAILED.value if failed else ArtStatus.SUCCESS.value
        self.run.completed_at = completed_at
        self.run.failure_reason = reason
        if self.run.started_at:
            elapsed = completed_at - self.run.started_at
            self.run.execution_time_ms = max(0, int(elapsed.total_seconds() * 1000))

    async def record_step(
        self,
        *,
        agent_name: str,
        step_name: str,
        status: str,
        confidence: float | None = None,
        confidence_reason: str | None = None,
        output_ref: str | None = None,
    ) -> AgentRunStep:
        self.step_sequence += 1
        now = datetime.now(UTC)
        step = AgentRunStep(
            agent_run_id=self.run.id,
            correlation_id=self.correlation_id,
            tenant_id=self.event.tenant_id,
            environment=self.environment,
            agent_name=agent_name,
            step_name=step_name,
            step_sequence=self.step_sequence,
            status=status,
            confidence_score=confidence,
            confidence_reason=confidence_reason,
            started_at=now,
            completed_at=now,
            execution_time_ms=0,
            output_ref=output_ref,
        )
        self.session.add(step)
        await self.session.flush()
        return step

    @staticmethod
    def _safe_payload_summary(payload: dict[str, Any]) -> dict[str, Any]:
        """Keep normalized diagnostic metadata and omit likely sensitive bodies."""

        excluded = {
            "request",
            "response",
            "body",
            "authorization",
            "token",
            "password",
            "secret",
        }
        return {key: value for key, value in payload.items() if key.lower() not in excluded}
