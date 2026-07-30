from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Event, Outbox
from app.schemas import CloudEventCreate, EventCreate
from app.security import Principal


async def persist_event(body: EventCreate, auth: Principal, session: AsyncSession) -> Event:
    """Persist an event and its outbox work atomically and idempotently."""

    existing = await session.scalar(select(Event).where(
        Event.tenant_id == auth.tenant_id, Event.external_id == body.external_id
    ))
    if existing:
        return existing
    event = Event(tenant_id=auth.tenant_id, **body.model_dump())
    session.add(event)
    await session.flush()
    session.add(Outbox(
        topic="event.received", aggregate_id=event.id, payload={"event_id": str(event.id)}
    ))
    session.add(AuditLog(
        tenant_id=auth.tenant_id, actor=auth.actor, action="event.received",
        resource_type="event", resource_id=str(event.id), details={"source": event.source},
    ))
    await session.commit()
    await session.refresh(event)
    return event


def cloud_event_to_event(body: CloudEventCreate) -> EventCreate:
    return EventCreate(
        external_id=body.id,
        event_type=body.type,
        source=body.source,
        severity=body.severity,
        correlation_key=body.correlationid or body.subject or body.id,
        payload={
            **body.data,
            "cloudevent": {
                "specversion": body.specversion,
                "subject": body.subject,
                "time": body.time.isoformat() if body.time else None,
                "dataschema": body.dataschema,
            },
        },
    )


async def persist_cloud_event(
    raw: dict[str, Any], auth: Principal, session: AsyncSession
) -> Event:
    body = CloudEventCreate.model_validate(raw)
    return await persist_event(cloud_event_to_event(body), auth, session)
