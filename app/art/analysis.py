"""Decision, impact, dependency, and test-selection routes."""

import uuid
from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.art.router import router
from app.art_models import (
    AgentDecisionJournal,
    ImpactAssessment,
    ImpactDependency,
    TestSelectionDecision,
)
from app.art_repository import ArtRepository
from app.art_schemas import (
    ArtResourceResponse,
    DecisionJournalCreate,
    ImpactAssessmentCreate,
    ImpactDependencyCreate,
    TestSelectionCreate,
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

@router.post("/decision-journals", response_model=ArtResourceResponse, status_code=201)
async def create_decision_journal(
    body: DecisionJournalCreate,
    auth: AuthenticatedUser,
    session: DatabaseSession,
):
    """Record one explainable agent decision."""
    return await repository(session, auth).create(AgentDecisionJournal, body)


@router.get("/decision-journals", response_model=list[ArtResourceResponse])
async def list_decision_journals(
    auth: AuthenticatedUser,
    session: DatabaseSession,
    correlation_id: uuid.UUID | None = None,
    environment: str | None = None,
    limit: PageLimit = api_settings.api_default_limit,
):
    """List tenant agent decision-journal records."""
    return await repository(session, auth).list(
        AgentDecisionJournal,
        correlation_id=correlation_id,
        environment=environment,
        limit=limit,
    )


@router.post("/impact-assessments", response_model=ArtResourceResponse, status_code=201)
async def create_impact_assessment(
    body: ImpactAssessmentCreate,
    auth: AuthenticatedUser,
    session: DatabaseSession,
):
    """Create an assessed impact record for a correlated failure."""
    return await repository(session, auth).create(ImpactAssessment, body)


@router.get("/impact-assessments", response_model=list[ArtResourceResponse])
async def list_impact_assessments(
    auth: AuthenticatedUser,
    session: DatabaseSession,
    correlation_id: uuid.UUID | None = None,
    environment: str | None = None,
    limit: PageLimit = api_settings.api_default_limit,
):
    """List tenant impact assessments with lifecycle filters."""
    return await repository(session, auth).list(
        ImpactAssessment,
        correlation_id=correlation_id,
        environment=environment,
        limit=limit,
    )


@router.post("/impact-dependencies", response_model=ArtResourceResponse, status_code=201)
async def create_impact_dependency(
    body: ImpactDependencyCreate,
    auth: AuthenticatedUser,
    session: DatabaseSession,
):
    """Attach one affected dependency to an impact assessment."""
    return await repository(session, auth).create(ImpactDependency, body)


@router.get("/impact-dependencies", response_model=list[ArtResourceResponse])
async def list_impact_dependencies(
    auth: AuthenticatedUser,
    session: DatabaseSession,
    correlation_id: uuid.UUID | None = None,
    environment: str | None = None,
    limit: PageLimit = api_settings.api_default_limit,
):
    """List tenant impact-dependency records."""
    return await repository(session, auth).list(
        ImpactDependency,
        correlation_id=correlation_id,
        environment=environment,
        limit=limit,
    )


@router.post("/test-selection-decisions", response_model=ArtResourceResponse, status_code=201)
async def create_test_selection(
    body: TestSelectionCreate,
    auth: AuthenticatedUser,
    session: DatabaseSession,
):
    """Record the governed tests selected for a proposed change."""
    return await repository(session, auth).create(TestSelectionDecision, body)


@router.get("/test-selection-decisions", response_model=list[ArtResourceResponse])
async def list_test_selections(
    auth: AuthenticatedUser,
    session: DatabaseSession,
    correlation_id: uuid.UUID | None = None,
    environment: str | None = None,
    limit: PageLimit = api_settings.api_default_limit,
):
    """List tenant test-selection decisions."""
    return await repository(session, auth).list(
        TestSelectionDecision,
        correlation_id=correlation_id,
        environment=environment,
        limit=limit,
    )
