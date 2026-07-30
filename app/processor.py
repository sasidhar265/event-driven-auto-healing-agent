import uuid
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.art_lifecycle import LifecycleRecorder
from app.models import (
    AuditLog, Event, EventStatus, Suggestion, SuggestionStatus,
    WebhookDelivery, WebhookSubscription,
)
from app.services import (
    AIService,
    Candidate,
    KnowledgeService,
    PolicyEngine,
    route_details,
    routed_agents,
)


async def process_event(session: AsyncSession, event_id: uuid.UUID) -> None:
    event = await session.scalar(
        select(Event).where(Event.id == event_id).with_for_update()
    )
    if not event or event.status == EventStatus.COMPLETED:
        return

    event.status = EventStatus.PROCESSING
    event.attempts += 1
    lifecycle = LifecycleRecorder(session, event)

    try:
        evidence = await KnowledgeService().search(session, event)
        route, agents = routed_agents(event)
        await lifecycle.start(route)

        _add_audit_log(
            session,
            event,
            actor="failure-router",
            action="event.classified",
            details=route_details(route),
        )

        suggestion_count = 0
        for agent in agents:
            candidate = await agent.suggest(event, evidence)
            if candidate is None:
                continue

            candidate = await AIService().enrich(event, candidate, evidence)
            candidate = replace(
                candidate,
                proposed_changes={
                    **candidate.proposed_changes,
                    "routing": route_details(route),
                },
            )

            suggestion = await _create_suggestion(
                session,
                event,
                candidate,
                evidence,
            )
            await lifecycle.record_candidate(candidate, suggestion)
            await _queue_ready_webhooks(session, event, suggestion)
            suggestion_count += 1

        event.status = EventStatus.COMPLETED
        event.processed_at = datetime.now(UTC)
        await lifecycle.complete()

        _add_audit_log(
            session,
            event,
            actor="event-runtime",
            action="event.processed",
            details={"suggestion_count": suggestion_count},
        )
    except Exception as exc:
        event.status = EventStatus.FAILED
        event.error = str(exc)[:2000]
        await lifecycle.complete(failed=True, reason=event.error)
        raise


async def _create_suggestion(
    session: AsyncSession,
    event: Event,
    candidate: Candidate,
    evidence: list[dict[str, Any]],
) -> Suggestion:
    status, policy_result, confidence = await PolicyEngine().evaluate(
        session,
        event,
        candidate,
    )
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


async def _queue_ready_webhooks(
    session: AsyncSession,
    event: Event,
    suggestion: Suggestion,
) -> None:
    if suggestion.status != SuggestionStatus.READY:
        return

    subscriptions = (
        await session.scalars(
            select(WebhookSubscription).where(
                WebhookSubscription.tenant_id == event.tenant_id,
                WebhookSubscription.active.is_(True),
            )
        )
    ).all()

    for subscription in subscriptions:
        accepts_ready_events = (
            "suggestion.ready" in subscription.event_types
            or "*" in subscription.event_types
        )
        if accepts_ready_events:
            session.add(
                WebhookDelivery(
                    tenant_id=event.tenant_id,
                    subscription_id=subscription.id,
                    suggestion_id=suggestion.id,
                )
            )


def _add_audit_log(
    session: AsyncSession,
    event: Event,
    *,
    actor: str,
    action: str,
    details: dict[str, Any],
) -> None:
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
