"""Tenant-scoped audit search endpoint."""

from datetime import datetime

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers import api_settings, operations_router
from app.db import get_session
from app.repositories.audit.queries import search_audit
from app.security import Principal, principal

@operations_router.get("/audit")
async def audit(
    limit: int = Query(
        api_settings.api_default_limit,
        ge=1,
        le=api_settings.api_max_limit,
    ),
    environment: str | None = Query(default=None, pattern="^(dev|test|preprod|prod)$"),
    from_time: datetime | None = None,
    to_time: datetime | None = None,
    correlation_id: str | None = Query(default=None, max_length=300),
    auth: Principal = Depends(principal),
    session: AsyncSession = Depends(get_session),
):
    """Search tenant audit history by time, environment, or correlation ID."""
    return await search_audit(
        session,
        auth.tenant_id,
        limit,
        environment,
        from_time,
        to_time,
        correlation_id,
    )
