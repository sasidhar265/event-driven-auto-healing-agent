"""Write operations for incident intake."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Event, Outbox
from app.schemas import EventCreate
from app.security import Principal


async def create_event(
    session: AsyncSession,
    body: EventCreate,
    principal: Principal,
) -> Event:
    """Idempotently create an event, outbox item, and audit row atomically."""
    existing = await session.scalar(
        select(Event).where(
            Event.tenant_id == principal.tenant_id,
            Event.external_id == body.external_id,
        )
    )
    if existing:
        return existing

    event = Event(tenant_id=principal.tenant_id, **body.model_dump())
    session.add(event)
    await session.flush()
    session.add(
        Outbox(
            topic="event.received",
            aggregate_id=event.id,
            payload={"event_id": str(event.id)},
        )
    )
    session.add(
        AuditLog(
            tenant_id=principal.tenant_id,
            actor=principal.actor,
            action="event.received",
            resource_type="event",
            resource_id=str(event.id),
            details={"source": event.source},
        )
    )
    await session.commit()
    await session.refresh(event)
    return event
