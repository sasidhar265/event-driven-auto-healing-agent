"""Write operations staged inside the processor's caller-owned transaction."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Event, Suggestion, WebhookDelivery, WebhookSubscription
from app.services import Candidate


async def create_suggestion(
    session: AsyncSession,
    event: Event,
    candidate: Candidate,
    evidence: list[dict[str, Any]],
    status,
    policy_result: dict[str, Any],
    confidence: float,
) -> Suggestion:
    """Stage a suggestion and its creation audit row, then return it."""
    suggestion = Suggestion(
        event_id=event.id,
        tenant_id=event.tenant_id,
        agent_type=candidate.agent_type,
        title=candidate.title,
        rationale=candidate.rationale,
        proposed_changes=candidate.proposed_changes,
        evidence=evidence,
        confidence=confidence,
        policy_result=policy_result,
        status=status,
    )
    session.add(suggestion)
    await session.flush()
    session.add(
        AuditLog(
            tenant_id=event.tenant_id,
            actor=f"agent:{candidate.agent_type}",
            action="suggestion.created",
            resource_type="suggestion",
            resource_id=str(suggestion.id),
            details={
                "event_id": str(event.id),
                "confidence": confidence,
                "status": status.value,
            },
        )
    )
    return suggestion


def queue_delivery(
    session: AsyncSession,
    event: Event,
    suggestion: Suggestion,
    subscription: WebhookSubscription,
) -> None:
    """Stage one webhook delivery in the processor transaction."""
    session.add(
        WebhookDelivery(
            tenant_id=event.tenant_id,
            subscription_id=subscription.id,
            suggestion_id=suggestion.id,
        )
    )


def add_event_audit(
    session: AsyncSession,
    event: Event,
    actor: str,
    action: str,
    details: dict[str, Any],
) -> None:
    """Stage one event audit row in the processor transaction."""
    session.add(
        AuditLog(
            tenant_id=event.tenant_id,
            actor=actor,
            action=action,
            resource_type="event",
            resource_id=str(event.id),
            details=details,
        )
    )
