"""Locking and lookup queries used by the event processor."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event, WebhookSubscription


async def lock_event(session: AsyncSession, event_id: uuid.UUID) -> Event | None:
    """Lock one event so concurrent workers cannot process it simultaneously."""
    return await session.scalar(
        select(Event).where(Event.id == event_id).with_for_update()
    )


async def list_active_subscriptions(
    session: AsyncSession, tenant_id: str
) -> list[WebhookSubscription]:
    """Return active webhook subscriptions for a tenant."""
    return list(
        (
            await session.scalars(
                select(WebhookSubscription).where(
                    WebhookSubscription.tenant_id == tenant_id,
                    WebhookSubscription.active.is_(True),
                )
            )
        ).all()
    )
