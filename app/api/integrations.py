"""Webhook subscription and delivery-management endpoints."""

import uuid

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers import api_settings, integration_router
from app.db import get_session
from app.repositories.delivery import commands as delivery_commands
from app.repositories.delivery import queries as delivery_queries
from app.schemas import SubscriptionCreate, SubscriptionRead
from app.security import Principal, principal

@integration_router.post("/subscriptions", response_model=SubscriptionRead, status_code=201)
async def create_subscription(body: SubscriptionCreate, auth: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    """Register and audit a tenant webhook subscription."""
    return await delivery_commands.create_subscription(session, auth, body)


@integration_router.get("/subscriptions", response_model=list[SubscriptionRead])
async def list_subscriptions(auth: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    """List all webhook subscriptions owned by the tenant."""
    return await delivery_queries.list_subscriptions(session, auth.tenant_id)


@integration_router.delete("/subscriptions/{subscription_id}", status_code=204)
async def deactivate_subscription(subscription_id: uuid.UUID, auth: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    """Deactivate and audit a tenant webhook subscription without deleting it."""
    changed = await delivery_commands.deactivate_subscription(
        session, auth, subscription_id
    )
    if not changed:
        raise HTTPException(404, "Subscription not found")


@integration_router.get("/deliveries")
async def list_deliveries(suggestion_id: uuid.UUID | None = None, auth: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    """List tenant webhook attempts, optionally for one suggestion."""
    rows = await delivery_queries.list_deliveries(
        session, auth.tenant_id, api_settings.api_delivery_limit, suggestion_id
    )
    return [{"id": row.id, "subscription_id": row.subscription_id, "suggestion_id": row.suggestion_id,
             "status": row.status, "attempts": row.attempts, "response_status": row.response_status,
             "last_error": row.last_error, "next_attempt_at": row.next_attempt_at,
             "delivered_at": row.delivered_at, "created_at": row.created_at} for row in rows]


@integration_router.post("/deliveries/{delivery_id}/retry", status_code=202)
async def retry_delivery(delivery_id: uuid.UUID, auth: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    """Make a failed tenant webhook delivery immediately eligible for retry."""
    item = await delivery_commands.retry_delivery(session, auth, delivery_id)
    if not item:
        raise HTTPException(404, "Delivery not found")
    return {"id": item.id, "status": item.status}
