"""Business logic for accepting or rejecting remediation suggestions."""

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AuditLog,
    Event,
    RemediationReference,
    Outbox,
    Suggestion,
    SuggestionDecision,
    SuggestionStatus,
)
from app.schemas import DecisionCreate
from app.security import Principal


def event_fingerprint(event: Event) -> str:
    """Return a stable identifier for failures with the same type and payload."""

    event_data = {
        "event_type": event.event_type,
        "payload": event.payload,
    }
    serialized = json.dumps(
        event_data,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode()).hexdigest()


async def record_suggestion_decision(
    session: AsyncSession,
    suggestion: Suggestion,
    event: Event,
    decision_request: DecisionCreate,
    principal: Principal,
) -> None:
    """Record a decision and keep the remediation reference library in sync."""

    decision_value = decision_request.decision
    queue_test_rerun = (
        decision_value == "accepted" and suggestion.status != SuggestionStatus.ACCEPTED
    )
    suggestion.status = SuggestionStatus(decision_value)

    await _upsert_decision(
        session,
        suggestion,
        decision_request,
        principal,
    )
    await _upsert_reference(
        session,
        suggestion,
        event,
        decision_request,
        principal,
    )

    session.add(
        AuditLog(
            tenant_id=principal.tenant_id,
            actor=principal.actor,
            action=f"suggestion.{decision_value}",
            resource_type="suggestion",
            resource_id=str(suggestion.id),
            details={"reason": decision_request.reason},
        )
    )
    if queue_test_rerun:
        session.add(
            Outbox(
                topic="test.rerun.requested",
                aggregate_id=suggestion.id,
                payload={
                    "suggestion_id": str(suggestion.id),
                    "event_id": str(event.id),
                },
            )
        )


async def _upsert_decision(
    session: AsyncSession,
    suggestion: Suggestion,
    decision_request: DecisionCreate,
    principal: Principal,
) -> None:
    """Create or update the single operator decision for a suggestion."""
    decision = await session.scalar(
        select(SuggestionDecision).where(SuggestionDecision.suggestion_id == suggestion.id)
    )

    if decision is None:
        decision = SuggestionDecision(
            suggestion_id=suggestion.id,
            tenant_id=principal.tenant_id,
            decision=decision_request.decision,
            reason=decision_request.reason,
            actor=principal.actor,
        )
        session.add(decision)
        return

    decision.decision = decision_request.decision
    decision.reason = decision_request.reason
    decision.actor = principal.actor


async def _upsert_reference(
    session: AsyncSession,
    suggestion: Suggestion,
    event: Event,
    decision_request: DecisionCreate,
    principal: Principal,
) -> None:
    """Synchronize reusable remediation learning with the latest decision."""
    reference = await session.scalar(
        select(RemediationReference).where(RemediationReference.suggestion_id == suggestion.id)
    )

    values = {
        "event_id": event.id,
        "tenant_id": principal.tenant_id,
        "event_type": event.event_type,
        "severity": event.severity,
        "fingerprint": event_fingerprint(event),
        "agent_type": suggestion.agent_type,
        "title": suggestion.title,
        "rationale": suggestion.rationale,
        "proposed_changes": suggestion.proposed_changes,
        "evidence": suggestion.evidence,
        "confidence": suggestion.confidence,
        "outcome": decision_request.decision,
        "decision_reason": decision_request.reason,
        "active": decision_request.decision == "accepted",
    }

    if reference is None:
        session.add(
            RemediationReference(
                suggestion_id=suggestion.id,
                **values,
            )
        )
        return

    for field, value in values.items():
        setattr(reference, field, value)
