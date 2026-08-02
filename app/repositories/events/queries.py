"""Read operations for tenant-owned incidents and their processing trace."""

import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Event, Suggestion


async def get_event(session: AsyncSession, event_id: uuid.UUID, tenant_id: str) -> Event | None:
    """Return one event only when it belongs to the requested tenant."""
    return await session.scalar(
        select(Event).where(Event.id == event_id, Event.tenant_id == tenant_id)
    )


async def list_events(session: AsyncSession, tenant_id: str, limit: int) -> list[Event]:
    """Return a tenant's newest events up to the supplied limit."""
    return list(
        (
            await session.scalars(
                select(Event)
                .where(Event.tenant_id == tenant_id)
                .order_by(Event.created_at.desc())
                .limit(limit)
            )
        ).all()
    )


async def get_trace_records(
    session: AsyncSession, event_id: uuid.UUID, tenant_id: str
) -> tuple[Event | None, list[Suggestion], list[AuditLog]]:
    """Return the source event and ordered suggestion/audit records for its trace."""
    event = await get_event(session, event_id, tenant_id)
    if event is None:
        return None, [], []
    suggestions = list(
        (
            await session.scalars(
                select(Suggestion)
                .where(
                    Suggestion.event_id == event.id,
                    Suggestion.tenant_id == tenant_id,
                )
                .order_by(Suggestion.created_at)
            )
        ).all()
    )
    audit_records = list(
        (
            await session.scalars(
                select(AuditLog)
                .where(
                    AuditLog.tenant_id == tenant_id,
                    or_(
                        (
                            (AuditLog.resource_type == "event")
                            & (AuditLog.resource_id == str(event.id))
                        ),
                        (
                            (AuditLog.resource_type == "suggestion")
                            & AuditLog.resource_id.in_([str(item.id) for item in suggestions])
                        ),
                    ),
                )
                .order_by(AuditLog.created_at)
            )
        ).all()
    )
    return event, suggestions, audit_records
