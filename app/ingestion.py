from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event
from app.repositories.events.commands import create_event
from app.schemas import CloudEventCreate, EventCreate
from app.security import Principal


async def persist_event(body: EventCreate, auth: Principal, session: AsyncSession) -> Event:
    """Persist an event and its outbox work atomically and idempotently."""

    return await create_event(session, body, auth)


def cloud_event_to_event(body: CloudEventCreate) -> EventCreate:
    """Convert a validated CloudEvent into ART's native incident contract."""
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
    """Validate raw CloudEvent data and persist it through normal event intake."""
    body = CloudEventCreate.model_validate(raw)
    return await persist_event(cloud_event_to_event(body), auth, session)
