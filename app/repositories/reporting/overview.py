"""Database projection for the operations overview."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Event, EventStatus, Suggestion, SuggestionStatus, WebhookDelivery


async def get_overview(
    session: AsyncSession,
    tenant_id: str,
    recent_event_limit: int,
    environment: str | None = None,
) -> dict[str, Any]:
    """Build tenant metrics and confidence classifications from PostgreSQL."""
    async def count(model, *criteria) -> int:
        """Count tenant rows for a model with optional additional predicates."""
        return int(await session.scalar(
            select(func.count()).select_from(model).where(
                model.tenant_id == tenant_id, *criteria
            )
        ) or 0)

    recent_query = select(Event).where(Event.tenant_id == tenant_id)
    if environment:
        recent_query = recent_query.where(
            Event.payload["environment"].astext == environment
        )
    recent_events = (
        await session.scalars(
            recent_query.order_by(Event.created_at.desc())
            .limit(recent_event_limit)
        )
    ).all()
    suggestion_query = (
        select(
            Suggestion.id,
            Suggestion.title,
            Suggestion.confidence,
            Suggestion.policy_result,
            Suggestion.status,
            Suggestion.created_at,
            Event.external_id,
            Event.correlation_key,
        )
        .join(Event, Event.id == Suggestion.event_id)
        .where(
            Suggestion.tenant_id == tenant_id,
            Event.tenant_id == tenant_id,
        )
    )
    if environment:
        suggestion_query = suggestion_query.where(
            Event.payload["environment"].astext == environment
        )
    suggestion_rows = (await session.execute(suggestion_query)).all()
    thresholds = get_settings()
    confidence_counts = {"suppressed": 0, "review": 0, "ready": 0}
    decision_records = []
    for (
        suggestion_id,
        title,
        confidence,
        policy_result,
        recorded_status,
        created_at,
        failure_id,
        correlation_id,
    ) in suggestion_rows:
        policy_result = policy_result or {}
        if policy_result.get("violations"):
            classification = "suppressed"
        elif (
            policy_result.get("approvals")
            or confidence < thresholds.confidence_delivery_threshold
        ):
            classification = (
                "review"
                if confidence >= thresholds.confidence_review_threshold
                else "suppressed"
            )
        else:
            classification = "ready"
        confidence_counts[classification] += 1
        decision_records.append({
            "suggestion_id": suggestion_id,
            "title": title,
            "confidence": confidence,
            "classification": classification,
            "recorded_status": recorded_status,
            "failure_id": failure_id,
            "correlation_id": correlation_id,
            "created_at": created_at,
        })
    decision_records.sort(key=lambda item: item["confidence"], reverse=True)

    return {
        "events": await count(Event),
        "processing": await count(
            Event, Event.status.in_([EventStatus.RECEIVED, EventStatus.PROCESSING])
        ),
        "suggestions": await count(Suggestion),
        "ready": await count(Suggestion, Suggestion.status == SuggestionStatus.READY),
        "review": await count(Suggestion, Suggestion.status == SuggestionStatus.REVIEW),
        "decision_model": {
            "thresholds": {
                "review": thresholds.confidence_review_threshold,
                "ready": thresholds.confidence_delivery_threshold,
            },
            "counts": confidence_counts,
            "total": len(suggestion_rows),
            "records": decision_records,
        },
        "dead_letters": await count(WebhookDelivery, WebhookDelivery.status == "dead_letter"),
        "recent_events": [
            {
                "id": row.id, "external_id": row.external_id,
                "event_type": row.event_type, "source": row.source,
                "environment": row.payload.get("environment", "unknown"),
                "severity": row.severity,
                "status": row.status, "created_at": row.created_at,
            }
            for row in recent_events
        ],
    }
