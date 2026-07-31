"""Read and locking queries for suggestions and remediation references."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event, RemediationReference, Suggestion


async def list_suggestions(
    session: AsyncSession,
    tenant_id: str,
    limit: int,
    event_id: uuid.UUID | None = None,
) -> list[Suggestion]:
    """Return newest tenant suggestions, optionally for one source event."""
    query = (
        select(Suggestion)
        .where(Suggestion.tenant_id == tenant_id)
        .order_by(Suggestion.created_at.desc())
    )
    if event_id:
        query = query.where(Suggestion.event_id == event_id)
    return list((await session.scalars(query.limit(limit))).all())


async def get_suggestion_for_update(
    session: AsyncSession, suggestion_id: uuid.UUID, tenant_id: str
) -> Suggestion | None:
    """Lock and return one tenant suggestion for a decision transaction."""
    return await session.scalar(
        select(Suggestion)
        .where(Suggestion.id == suggestion_id, Suggestion.tenant_id == tenant_id)
        .with_for_update()
    )


async def get_source_event(
    session: AsyncSession, event_id: uuid.UUID, tenant_id: str
) -> Event | None:
    """Return the tenant-owned source event for a suggestion."""
    return await session.scalar(
        select(Event).where(Event.id == event_id, Event.tenant_id == tenant_id)
    )


async def list_references(
    session: AsyncSession, tenant_id: str, limit: int, active_only: bool = True
) -> list[RemediationReference]:
    """Return newest reusable remediation references for a tenant."""
    query = select(RemediationReference).where(
        RemediationReference.tenant_id == tenant_id
    )
    if active_only:
        query = query.where(RemediationReference.active.is_(True))
    return list(
        (
            await session.scalars(
                query.order_by(RemediationReference.created_at.desc()).limit(limit)
            )
        ).all()
    )
