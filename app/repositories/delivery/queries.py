"""Read operations for webhook subscriptions and delivery attempts."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import WebhookDelivery, WebhookSubscription


async def list_subscriptions(
    session: AsyncSession, tenant_id: str
) -> list[WebhookSubscription]:
    """Return all tenant subscriptions, newest first."""
    return list(
        (
            await session.scalars(
                select(WebhookSubscription)
                .where(WebhookSubscription.tenant_id == tenant_id)
                .order_by(WebhookSubscription.created_at.desc())
            )
        ).all()
    )


async def list_deliveries(
    session: AsyncSession,
    tenant_id: str,
    limit: int,
    suggestion_id: uuid.UUID | None = None,
) -> list[WebhookDelivery]:
    """Return tenant deliveries, optionally for one suggestion."""
    query = select(WebhookDelivery).where(WebhookDelivery.tenant_id == tenant_id)
    if suggestion_id:
        query = query.where(WebhookDelivery.suggestion_id == suggestion_id)
    return list(
        (
            await session.scalars(
                query.order_by(WebhookDelivery.created_at.desc()).limit(limit)
            )
        ).all()
    )
