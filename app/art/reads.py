"""Shared resource reads and correlation-trace route registration."""

import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.art.router import router
from app.art_models import (
    AgentDecisionJournal,
    AgentRun,
    AgentRunStep,
    ArtEventInbox,
    ArtEventOutbox,
    ExecutionIntent,
    ExecutionResultRef,
    FailureEvent,
    ImpactAssessment,
    ImpactDependency,
    OutcomeFeedback,
    SelfHealProposal,
    TestSelectionDecision,
)
from app.art_repository import ArtRepository
from app.art_schemas import ArtResourceResponse
from app.db import get_session
from app.security import Principal, principal

AuthenticatedUser = Annotated[Principal, Depends(principal)]
DatabaseSession = Annotated[AsyncSession, Depends(get_session)]


def repository(session: AsyncSession, auth: Principal) -> ArtRepository:
    """Build the tenant-aware data access object used by a route."""
    return ArtRepository(session, auth)

def _register_resource_read_route(
    resource: str,
    model: type[DeclarativeBase],
) -> None:
    """Register a tenant-safe GET-by-ID route for a lifecycle model."""
    async def read_resource(
        record_id: uuid.UUID,
        auth: AuthenticatedUser,
        session: DatabaseSession,
    ):
        """Read one tenant-owned lifecycle resource through the repository."""
        return await repository(session, auth).get(model, record_id)

    read_resource.__name__ = f"get_{resource.replace('-', '_')}"
    router.add_api_route(
        f"/{resource}/{{record_id}}",
        read_resource,
        methods=["GET"],
        response_model=ArtResourceResponse,
        summary=f"Get one {resource.replace('-', ' ')} record",
    )


for _resource, _model in {
    "failure-events": FailureEvent,
    "agent-runs": AgentRun,
    "agent-run-steps": AgentRunStep,
    "decision-journals": AgentDecisionJournal,
    "impact-assessments": ImpactAssessment,
    "impact-dependencies": ImpactDependency,
    "test-selection-decisions": TestSelectionDecision,
    "execution-intents": ExecutionIntent,
    "execution-result-refs": ExecutionResultRef,
    "self-heal-proposals": SelfHealProposal,
    "outcome-feedback": OutcomeFeedback,
    "event-inbox": ArtEventInbox,
    "event-outbox": ArtEventOutbox,
}.items():
    _register_resource_read_route(_resource, _model)


@router.get("/correlations/{correlation_id}")
async def correlation_trace(
    correlation_id: uuid.UUID,
    auth: AuthenticatedUser,
    session: DatabaseSession,
):
    """Return the complete tenant lifecycle trace for one correlation UUID."""
    return await repository(session, auth).correlation_trace(correlation_id)
