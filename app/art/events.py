"""Lifecycle inbox and outbox routes."""

import uuid
from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.art.router import router
from app.art_models import (
    ArtEventInbox,
    ArtEventOutbox,
)
from app.art_repository import ArtRepository
from app.art_schemas import (
    ArtResourceResponse,
    EventInboxCreate,
    EventOutboxCreate,
)
from app.config import get_settings
from app.db import get_session
from app.security import Principal, principal

api_settings = get_settings()
AuthenticatedUser = Annotated[Principal, Depends(principal)]
DatabaseSession = Annotated[AsyncSession, Depends(get_session)]
PageLimit = Annotated[int, Query(ge=1, le=api_settings.api_max_limit)]


def repository(session: AsyncSession, auth: Principal) -> ArtRepository:
    """Build the tenant-aware data access object used by a route."""
    return ArtRepository(session, auth)

@router.post("/event-inbox", response_model=ArtResourceResponse, status_code=201)
async def create_event_inbox(
    body: EventInboxCreate,
    auth: AuthenticatedUser,
    session: DatabaseSession,
):
    """Record receipt and idempotency state for a lifecycle event."""
    return await repository(session, auth).create(ArtEventInbox, body)


@router.get("/event-inbox", response_model=list[ArtResourceResponse])
async def list_event_inbox(
    auth: AuthenticatedUser,
    session: DatabaseSession,
    correlation_id: uuid.UUID | None = None,
    environment: str | None = None,
    limit: PageLimit = api_settings.api_default_limit,
):
    """List tenant lifecycle inbox records."""
    return await repository(session, auth).list(
        ArtEventInbox,
        correlation_id=correlation_id,
        environment=environment,
        limit=limit,
    )


@router.post("/event-outbox", response_model=ArtResourceResponse, status_code=201)
async def create_event_outbox(
    body: EventOutboxCreate,
    auth: AuthenticatedUser,
    session: DatabaseSession,
):
    """Create a durable lifecycle event awaiting publication."""
    return await repository(session, auth).create(ArtEventOutbox, body)


@router.get("/event-outbox", response_model=list[ArtResourceResponse])
async def list_event_outbox(
    auth: AuthenticatedUser,
    session: DatabaseSession,
    correlation_id: uuid.UUID | None = None,
    environment: str | None = None,
    limit: PageLimit = api_settings.api_default_limit,
):
    """List tenant lifecycle outbox records."""
    return await repository(session, auth).list(
        ArtEventOutbox,
        correlation_id=correlation_id,
        environment=environment,
        limit=limit,
    )
