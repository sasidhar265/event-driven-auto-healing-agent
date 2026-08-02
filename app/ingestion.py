from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event
from app.repositories.events.commands import create_event
from app.schemas import CloudEventCreate, EventCreate
from app.security import Principal
from app.services.runtime_intelligence import (
    incident_fingerprint,
    normalize_incident,
    score_business_impact,
)


async def persist_event(body: EventCreate, auth: Principal, session: AsyncSession) -> Event:
    """Persist an event and its outbox work atomically and idempotently."""
    context = normalize_incident(
        event_type=body.event_type,
        source=body.source,
        severity=body.severity,
        payload=body.payload,
    )
    enriched = body.model_copy(
        update={
            "payload": {
                **body.payload,
                "art_context": context,
                "art_incident_fingerprint": incident_fingerprint(context),
                "art_business_impact": score_business_impact(context),
            }
        }
    )
    return await create_event(session, enriched, auth)


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


async def persist_cloud_event(raw: dict[str, Any], auth: Principal, session: AsyncSession) -> Event:
    """Validate raw CloudEvent data and persist it through normal event intake."""
    body = CloudEventCreate.model_validate(raw)
    return await persist_event(cloud_event_to_event(body), auth, session)
