"""Failure-event and agent-run lifecycle routes."""

import uuid
from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.art.router import router
from app.art_models import (
    AgentRun,
    AgentRunStep,
    FailureEvent,
)
from app.art_repository import ArtRepository
from app.art_schemas import (
    AgentRunCreate,
    AgentRunStepCreate,
    ArtResourceResponse,
    FailureEventCreate,
    LifecycleStateUpdate,
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

@router.post("/failure-events", response_model=ArtResourceResponse, status_code=201)
async def create_failure_event(
    body: FailureEventCreate,
    auth: AuthenticatedUser,
    session: DatabaseSession,
):
    """Create and audit one governed failure-event record."""
    return await repository(session, auth).create(FailureEvent, body)


@router.get("/failure-events", response_model=list[ArtResourceResponse])
async def list_failure_events(
    auth: AuthenticatedUser,
    session: DatabaseSession,
    correlation_id: uuid.UUID | None = None,
    environment: str | None = None,
    limit: PageLimit = api_settings.api_default_limit,
):
    """List tenant failure events with lifecycle filters."""
    return await repository(session, auth).list(
        FailureEvent,
        correlation_id=correlation_id,
        environment=environment,
        limit=limit,
    )


@router.post("/agent-runs", response_model=ArtResourceResponse, status_code=201)
async def create_agent_run(
    body: AgentRunCreate,
    auth: AuthenticatedUser,
    session: DatabaseSession,
):
    """Create and audit one agent workflow run."""
    return await repository(session, auth).create(AgentRun, body)


@router.get("/agent-runs", response_model=list[ArtResourceResponse])
async def list_agent_runs(
    auth: AuthenticatedUser,
    session: DatabaseSession,
    correlation_id: uuid.UUID | None = None,
    environment: str | None = None,
    limit: PageLimit = api_settings.api_default_limit,
):
    """List tenant agent runs with lifecycle filters."""
    return await repository(session, auth).list(
        AgentRun,
        correlation_id=correlation_id,
        environment=environment,
        limit=limit,
    )


@router.patch("/agent-runs/{record_id}/state", response_model=ArtResourceResponse)
async def update_agent_run(
    record_id: uuid.UUID,
    body: LifecycleStateUpdate,
    auth: AuthenticatedUser,
    session: DatabaseSession,
):
    """Apply an audited state transition to an agent run."""
    return await repository(session, auth).change_state(AgentRun, record_id, body)


@router.post("/agent-run-steps", response_model=ArtResourceResponse, status_code=201)
async def create_agent_run_step(
    body: AgentRunStepCreate,
    auth: AuthenticatedUser,
    session: DatabaseSession,
):
    """Create one traceable step within an agent run."""
    return await repository(session, auth).create(AgentRunStep, body)


@router.get("/agent-run-steps", response_model=list[ArtResourceResponse])
async def list_agent_run_steps(
    auth: AuthenticatedUser,
    session: DatabaseSession,
    correlation_id: uuid.UUID | None = None,
    environment: str | None = None,
    limit: PageLimit = api_settings.api_default_limit,
):
    """List tenant agent-run steps with lifecycle filters."""
    return await repository(session, auth).list(
        AgentRunStep,
        correlation_id=correlation_id,
        environment=environment,
        limit=limit,
    )
