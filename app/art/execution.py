"""Execution, self-healing, and outcome lifecycle routes."""

import uuid
from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.art.router import router
from app.art_models import (
    ExecutionIntent,
    ExecutionResultRef,
    OutcomeFeedback,
    SelfHealProposal,
)
from app.art_repository import ArtRepository
from app.art_schemas import (
    ArtResourceResponse,
    ExecutionIntentCreate,
    ExecutionResultCreate,
    LifecycleStateUpdate,
    OutcomeFeedbackCreate,
    SelfHealProposalCreate,
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

@router.post("/execution-intents", response_model=ArtResourceResponse, status_code=201)
async def create_execution_intent(
    body: ExecutionIntentCreate,
    auth: AuthenticatedUser,
    session: DatabaseSession,
):
    """Create a governed request to execute a selected action."""
    return await repository(session, auth).create(ExecutionIntent, body)


@router.get("/execution-intents", response_model=list[ArtResourceResponse])
async def list_execution_intents(
    auth: AuthenticatedUser,
    session: DatabaseSession,
    correlation_id: uuid.UUID | None = None,
    environment: str | None = None,
    limit: PageLimit = api_settings.api_default_limit,
):
    """List tenant execution intents with lifecycle filters."""
    return await repository(session, auth).list(
        ExecutionIntent,
        correlation_id=correlation_id,
        environment=environment,
        limit=limit,
    )


@router.patch("/execution-intents/{record_id}/state", response_model=ArtResourceResponse)
async def update_execution_intent(
    record_id: uuid.UUID,
    body: LifecycleStateUpdate,
    auth: AuthenticatedUser,
    session: DatabaseSession,
):
    """Apply a governance-checked execution-intent state transition."""
    return await repository(session, auth).change_state(ExecutionIntent, record_id, body)


@router.post("/execution-result-refs", response_model=ArtResourceResponse, status_code=201)
async def create_execution_result(
    body: ExecutionResultCreate,
    auth: AuthenticatedUser,
    session: DatabaseSession,
):
    """Record a reference to an execution result or artifact."""
    return await repository(session, auth).create(ExecutionResultRef, body)


@router.get("/execution-result-refs", response_model=list[ArtResourceResponse])
async def list_execution_results(
    auth: AuthenticatedUser,
    session: DatabaseSession,
    correlation_id: uuid.UUID | None = None,
    environment: str | None = None,
    limit: PageLimit = api_settings.api_default_limit,
):
    """List tenant execution-result references."""
    return await repository(session, auth).list(
        ExecutionResultRef,
        correlation_id=correlation_id,
        environment=environment,
        limit=limit,
    )


@router.post("/self-heal-proposals", response_model=ArtResourceResponse, status_code=201)
async def create_self_heal_proposal(
    body: SelfHealProposalCreate,
    auth: AuthenticatedUser,
    session: DatabaseSession,
):
    """Create a governed self-healing proposal without executing it."""
    return await repository(session, auth).create(SelfHealProposal, body)


@router.get("/self-heal-proposals", response_model=list[ArtResourceResponse])
async def list_self_heal_proposals(
    auth: AuthenticatedUser,
    session: DatabaseSession,
    correlation_id: uuid.UUID | None = None,
    environment: str | None = None,
    limit: PageLimit = api_settings.api_default_limit,
):
    """List tenant self-healing proposals."""
    return await repository(session, auth).list(
        SelfHealProposal,
        correlation_id=correlation_id,
        environment=environment,
        limit=limit,
    )


@router.patch("/self-heal-proposals/{record_id}/state", response_model=ArtResourceResponse)
async def update_self_heal_proposal(
    record_id: uuid.UUID,
    body: LifecycleStateUpdate,
    auth: AuthenticatedUser,
    session: DatabaseSession,
):
    """Apply an audited, governance-checked proposal state transition."""
    return await repository(session, auth).change_state(SelfHealProposal, record_id, body)


@router.post("/outcome-feedback", response_model=ArtResourceResponse, status_code=201)
async def create_outcome_feedback(
    body: OutcomeFeedbackCreate,
    auth: AuthenticatedUser,
    session: DatabaseSession,
):
    """Record observed outcome feedback for lifecycle learning."""
    return await repository(session, auth).create(OutcomeFeedback, body)


@router.get("/outcome-feedback", response_model=list[ArtResourceResponse])
async def list_outcome_feedback(
    auth: AuthenticatedUser,
    session: DatabaseSession,
    correlation_id: uuid.UUID | None = None,
    environment: str | None = None,
    limit: PageLimit = api_settings.api_default_limit,
):
    """List tenant outcome-feedback records."""
    return await repository(session, auth).list(
        OutcomeFeedback,
        correlation_id=correlation_id,
        environment=environment,
        limit=limit,
    )
