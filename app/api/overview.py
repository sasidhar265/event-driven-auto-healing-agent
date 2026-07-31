"""Operational overview and confidence-decision metrics endpoint."""

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers import api_settings, operations_router
from app.db import get_session
from app.repositories.reporting.overview import get_overview
from app.security import Principal, principal

@operations_router.get("/overview")
async def overview(
    environment: str | None = Query(default=None, pattern="^(dev|test|preprod|prod)$"),
    auth: Principal = Depends(principal),
    session: AsyncSession = Depends(get_session),
):
    """Build event, suggestion, confidence, and delivery metrics for the UI."""
    return await get_overview(
        session,
        auth.tenant_id,
        api_settings.api_recent_event_limit,
        environment,
    )
