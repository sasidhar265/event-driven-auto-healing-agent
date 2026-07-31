"""Tenant-scoped audit reporting queries."""

from datetime import datetime
from typing import Any

from sqlalchemy import String, and_, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Event, Suggestion


async def search_audit(
    session: AsyncSession,
    tenant_id: str,
    limit: int,
    environment: str | None = None,
    from_time: datetime | None = None,
    to_time: datetime | None = None,
    correlation_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return enriched tenant audit rows matching operational filters."""
    query = select(AuditLog).where(AuditLog.tenant_id == tenant_id)
    if from_time:
        query = query.where(AuditLog.created_at >= from_time)
    if to_time:
        query = query.where(AuditLog.created_at <= to_time)
    normalized_correlation_id = correlation_id.strip() if correlation_id else None
    if environment or normalized_correlation_id:
        event_filters = [Event.tenant_id == tenant_id]
        if environment:
            event_filters.append(Event.payload["environment"].astext == environment)
        if normalized_correlation_id:
            event_filters.append(Event.correlation_key.ilike(f"%{normalized_correlation_id}%"))

        environment_events = select(cast(Event.id, String)).where(*event_filters)
        environment_suggestions = (
            select(cast(Suggestion.id, String))
            .join(Event, Event.id == Suggestion.event_id)
            .where(
                Suggestion.tenant_id == tenant_id,
                *event_filters,
            )
        )
        query = query.where(
            or_(
                and_(
                    AuditLog.resource_type == "event",
                    AuditLog.resource_id.in_(environment_events),
                ),
                and_(
                    AuditLog.resource_type == "suggestion",
                    AuditLog.resource_id.in_(environment_suggestions),
                ),
            )
        )
    rows = (
        await session.scalars(query.order_by(AuditLog.created_at.desc()).limit(limit))
    ).all()

    event_resource_ids = [
        row.resource_id for row in rows if row.resource_type == "event"
    ]
    suggestion_resource_ids = [
        row.resource_id for row in rows if row.resource_type == "suggestion"
    ]
    event_identifiers = {}
    if event_resource_ids:
        event_rows = await session.execute(
            select(Event.id, Event.correlation_key, Event.external_id).where(
                Event.tenant_id == tenant_id,
                cast(Event.id, String).in_(event_resource_ids),
            )
        )
        event_identifiers.update(
            {
                str(event_id): {
                    "correlation_id": correlation_key,
                    "failure_id": external_id,
                }
                for event_id, correlation_key, external_id in event_rows
            }
        )
    if suggestion_resource_ids:
        suggestion_rows = await session.execute(
            select(
                Suggestion.id,
                Event.correlation_key,
                Event.external_id,
            )
            .join(Event, Event.id == Suggestion.event_id)
            .where(
                Suggestion.tenant_id == tenant_id,
                Event.tenant_id == tenant_id,
                cast(Suggestion.id, String).in_(suggestion_resource_ids),
            )
        )
        event_identifiers.update(
            {
                str(suggestion_id): {
                    "correlation_id": correlation_key,
                    "failure_id": external_id,
                }
                for suggestion_id, correlation_key, external_id in suggestion_rows
            }
        )

    return [
        {
            "id": row.id,
            "actor": row.actor,
            "action": row.action,
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            **event_identifiers.get(row.resource_id, {
                "correlation_id": None,
                "failure_id": None,
            }),
            "details": row.details,
            "created_at": row.created_at,
        }
        for row in rows
    ]
