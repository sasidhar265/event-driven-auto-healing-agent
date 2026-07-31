"""Write operations for webhook subscriptions and delivery retries."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, WebhookDelivery, WebhookSubscription
from app.schemas import SubscriptionCreate
from app.security import Principal


async def create_subscription(
    session: AsyncSession, principal: Principal, body: SubscriptionCreate
) -> WebhookSubscription:
    """Create, audit, and commit one tenant webhook subscription."""
    item = WebhookSubscription(tenant_id=principal.tenant_id, **body.model_dump())
    session.add(item)
    await session.flush()
    session.add(
        AuditLog(
            tenant_id=principal.tenant_id,
            actor=principal.actor,
            action="subscription.created",
            resource_type="webhook_subscription",
            resource_id=str(item.id),
            details={"callback_url": item.callback_url, "event_types": item.event_types},
        )
    )
    await session.commit()
    await session.refresh(item)
    return item


async def deactivate_subscription(
    session: AsyncSession, principal: Principal, subscription_id: uuid.UUID
) -> bool:
    """Lock, deactivate, audit, and commit a tenant subscription."""
    item = await session.scalar(
        select(WebhookSubscription)
        .where(
            WebhookSubscription.id == subscription_id,
            WebhookSubscription.tenant_id == principal.tenant_id,
        )
        .with_for_update()
    )
    if item is None:
        return False
    item.active = False
    session.add(
        AuditLog(
            tenant_id=principal.tenant_id,
            actor=principal.actor,
            action="subscription.deactivated",
            resource_type="webhook_subscription",
            resource_id=str(item.id),
            details={},
        )
    )
    await session.commit()
    return True


async def retry_delivery(
    session: AsyncSession, principal: Principal, delivery_id: uuid.UUID
) -> WebhookDelivery | None:
    """Lock a delivery, reset retry state, audit, and commit the request."""
    item = await session.scalar(
        select(WebhookDelivery)
        .where(
            WebhookDelivery.id == delivery_id,
            WebhookDelivery.tenant_id == principal.tenant_id,
        )
        .with_for_update()
    )
    if item is None:
        return None
    item.status = "retry"
    item.next_attempt_at = datetime.now(UTC)
    item.last_error = None
    session.add(
        AuditLog(
            tenant_id=principal.tenant_id,
            actor=principal.actor,
            action="webhook.retry_requested",
            resource_type="webhook_delivery",
            resource_id=str(item.id),
            details={},
        )
    )
    await session.commit()
    return item
