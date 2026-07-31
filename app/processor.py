import uuid
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.art_lifecycle import LifecycleRecorder
from app.models import Event, EventStatus, Suggestion, SuggestionStatus
from app.repositories.processing import commands as processing_commands
from app.repositories.processing import queries as processing_queries
from app.runtime_config import get_runtime_rules
from app.services import (
    AIService,
    Candidate,
    KnowledgeService,
    PolicyEngine,
    route_details,
    routed_agents,
)


async def process_event(session: AsyncSession, event_id: uuid.UUID) -> None:
    """Turn one locked event into governed suggestions and lifecycle records.

    The caller owns the transaction. Completed or missing events are ignored;
    processing failures mark the event failed and are re-raised for the worker.
    """
    rules = get_runtime_rules()
    event = await processing_queries.lock_event(session, event_id)
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
            actor=rules.lifecycle.runtime_actor,
            action="event.processed",
            details={"suggestion_count": suggestion_count},
        )
    except Exception as exc:
        event.status = EventStatus.FAILED
        event.error = str(exc)[
            :get_runtime_rules().delivery.error_message_max_length
        ]
        await lifecycle.complete(failed=True, reason=event.error)
        raise


async def _create_suggestion(
    session: AsyncSession,
    event: Event,
    candidate: Candidate,
    evidence: list[dict[str, Any]],
) -> Suggestion:
    """Apply policy/confidence and persist a suggestion with its audit record."""
    status, policy_result, confidence = await PolicyEngine().evaluate(
        session,
        event,
        candidate,
    )
    return await processing_commands.create_suggestion(
        session, event, candidate, evidence, status, policy_result, confidence
    )


async def _queue_ready_webhooks(
    session: AsyncSession,
    event: Event,
    suggestion: Suggestion,
) -> None:
    """Queue deliveries for active subscriptions that accept ready suggestions."""
    ready_event_type = get_runtime_rules().delivery.cloud_event_type
    if suggestion.status != SuggestionStatus.READY:
        return

    subscriptions = await processing_queries.list_active_subscriptions(
        session, event.tenant_id
    )

    for subscription in subscriptions:
        accepts_ready_events = (
            ready_event_type in subscription.event_types
            or "*" in subscription.event_types
        )
        if accepts_ready_events:
            processing_commands.queue_delivery(session, event, suggestion, subscription)


def _add_audit_log(
    session: AsyncSession,
    event: Event,
    *,
    actor: str,
    action: str,
    details: dict[str, Any],
) -> None:
    """Stage an event-level audit record in the caller's transaction."""
    processing_commands.add_event_audit(session, event, actor, action, details)
