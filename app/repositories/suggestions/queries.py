"""Read and locking queries for suggestions and remediation references."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event, RemediationReference, Suggestion, SuggestionStatus


async def list_suggestions(
    session: AsyncSession,
    tenant_id: str,
    limit: int,
    event_id: uuid.UUID | None = None,
    correlation_id: str | None = None,
    status: SuggestionStatus | None = None,
    offset: int = 0,
) -> list[Suggestion]:
    """Return newest tenant suggestions with their source correlation IDs."""
    query = (
        select(Suggestion, Event.correlation_key)
        .join(Event, Event.id == Suggestion.event_id)
        .where(Suggestion.tenant_id == tenant_id)
        .order_by(Suggestion.created_at.desc())
    )
    if event_id:
        query = query.where(Suggestion.event_id == event_id)
    if correlation_id:
        query = query.where(Event.correlation_key.ilike(f"%{correlation_id}%"))
    if status:
        query = query.where(Suggestion.status == status)
    rows = (await session.execute(query.offset(offset).limit(limit))).all()
    suggestions = []
    for suggestion, correlation_key in rows:
        suggestion.correlation_id = correlation_key
        suggestions.append(suggestion)
    return suggestions


async def count_suggestions_by_status(
    session: AsyncSession,
    tenant_id: str,
    event_id: uuid.UUID | None = None,
    correlation_id: str | None = None,
) -> dict[str, int]:
    """Count matching tenant suggestions by lifecycle status."""
    query = (
        select(Suggestion.status, func.count(Suggestion.id))
        .join(Event, Event.id == Suggestion.event_id)
        .where(Suggestion.tenant_id == tenant_id)
        .group_by(Suggestion.status)
    )
    if event_id:
        query = query.where(Suggestion.event_id == event_id)
    if correlation_id:
        query = query.where(Event.correlation_key.ilike(f"%{correlation_id}%"))
    rows = (await session.execute(query)).all()
    counts = {status.value: count for status, count in rows}
    counts["all"] = sum(counts.values())
    return counts


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
