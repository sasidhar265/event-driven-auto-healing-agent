"""HTTP routes for the tenant-scoped ART lifecycle API."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

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
from app.art_schemas import (
    AgentRunCreate,
    AgentRunStepCreate,
    ArtResourceResponse,
    DecisionJournalCreate,
    EventInboxCreate,
    EventOutboxCreate,
    ExecutionIntentCreate,
    ExecutionResultCreate,
    FailureEventCreate,
    ImpactAssessmentCreate,
    ImpactDependencyCreate,
    LifecycleStateUpdate,
    OutcomeFeedbackCreate,
    SelfHealProposalCreate,
    TestSelectionCreate,
)
from app.config import get_settings
from app.db import get_session
from app.security import Principal, principal

router = APIRouter(prefix="/v1/art", tags=["ART lifecycle"])
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
    return await repository(session, auth).create(FailureEvent, body)


@router.get("/failure-events", response_model=list[ArtResourceResponse])
async def list_failure_events(
    auth: AuthenticatedUser,
    session: DatabaseSession,
    correlation_id: uuid.UUID | None = None,
    environment: str | None = None,
    limit: PageLimit = api_settings.api_default_limit,
):
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
    return await repository(session, auth).create(AgentRun, body)


@router.get("/agent-runs", response_model=list[ArtResourceResponse])
async def list_agent_runs(
    auth: AuthenticatedUser,
    session: DatabaseSession,
    correlation_id: uuid.UUID | None = None,
    environment: str | None = None,
    limit: PageLimit = api_settings.api_default_limit,
):
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
    return await repository(session, auth).change_state(AgentRun, record_id, body)


@router.post("/agent-run-steps", response_model=ArtResourceResponse, status_code=201)
async def create_agent_run_step(
    body: AgentRunStepCreate,
    auth: AuthenticatedUser,
    session: DatabaseSession,
):
    return await repository(session, auth).create(AgentRunStep, body)


@router.get("/agent-run-steps", response_model=list[ArtResourceResponse])
async def list_agent_run_steps(
    auth: AuthenticatedUser,
    session: DatabaseSession,
    correlation_id: uuid.UUID | None = None,
    environment: str | None = None,
    limit: PageLimit = api_settings.api_default_limit,
):
    return await repository(session, auth).list(
        AgentRunStep,
        correlation_id=correlation_id,
        environment=environment,
        limit=limit,
    )


@router.post("/decision-journals", response_model=ArtResourceResponse, status_code=201)
async def create_decision_journal(
    body: DecisionJournalCreate,
    auth: AuthenticatedUser,
    session: DatabaseSession,
):
    return await repository(session, auth).create(AgentDecisionJournal, body)


@router.get("/decision-journals", response_model=list[ArtResourceResponse])
async def list_decision_journals(
    auth: AuthenticatedUser,
    session: DatabaseSession,
    correlation_id: uuid.UUID | None = None,
    environment: str | None = None,
    limit: PageLimit = api_settings.api_default_limit,
):
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
    return await repository(session, auth).create(ImpactAssessment, body)


@router.get("/impact-assessments", response_model=list[ArtResourceResponse])
async def list_impact_assessments(
    auth: AuthenticatedUser,
    session: DatabaseSession,
    correlation_id: uuid.UUID | None = None,
    environment: str | None = None,
    limit: PageLimit = api_settings.api_default_limit,
):
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
    return await repository(session, auth).create(ImpactDependency, body)


@router.get("/impact-dependencies", response_model=list[ArtResourceResponse])
async def list_impact_dependencies(
    auth: AuthenticatedUser,
    session: DatabaseSession,
    correlation_id: uuid.UUID | None = None,
    environment: str | None = None,
    limit: PageLimit = api_settings.api_default_limit,
):
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
    return await repository(session, auth).create(TestSelectionDecision, body)


@router.get("/test-selection-decisions", response_model=list[ArtResourceResponse])
async def list_test_selections(
    auth: AuthenticatedUser,
    session: DatabaseSession,
    correlation_id: uuid.UUID | None = None,
    environment: str | None = None,
    limit: PageLimit = api_settings.api_default_limit,
):
    return await repository(session, auth).list(
        TestSelectionDecision,
        correlation_id=correlation_id,
        environment=environment,
        limit=limit,
    )


@router.post("/execution-intents", response_model=ArtResourceResponse, status_code=201)
async def create_execution_intent(
    body: ExecutionIntentCreate,
    auth: AuthenticatedUser,
    session: DatabaseSession,
):
    return await repository(session, auth).create(ExecutionIntent, body)


@router.get("/execution-intents", response_model=list[ArtResourceResponse])
async def list_execution_intents(
    auth: AuthenticatedUser,
    session: DatabaseSession,
    correlation_id: uuid.UUID | None = None,
    environment: str | None = None,
    limit: PageLimit = api_settings.api_default_limit,
):
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
    return await repository(session, auth).change_state(ExecutionIntent, record_id, body)


@router.post("/execution-result-refs", response_model=ArtResourceResponse, status_code=201)
async def create_execution_result(
    body: ExecutionResultCreate,
    auth: AuthenticatedUser,
    session: DatabaseSession,
):
    return await repository(session, auth).create(ExecutionResultRef, body)


@router.get("/execution-result-refs", response_model=list[ArtResourceResponse])
async def list_execution_results(
    auth: AuthenticatedUser,
    session: DatabaseSession,
    correlation_id: uuid.UUID | None = None,
    environment: str | None = None,
    limit: PageLimit = api_settings.api_default_limit,
):
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
    return await repository(session, auth).create(SelfHealProposal, body)


@router.get("/self-heal-proposals", response_model=list[ArtResourceResponse])
async def list_self_heal_proposals(
    auth: AuthenticatedUser,
    session: DatabaseSession,
    correlation_id: uuid.UUID | None = None,
    environment: str | None = None,
    limit: PageLimit = api_settings.api_default_limit,
):
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
    return await repository(session, auth).change_state(SelfHealProposal, record_id, body)


@router.post("/outcome-feedback", response_model=ArtResourceResponse, status_code=201)
async def create_outcome_feedback(
    body: OutcomeFeedbackCreate,
    auth: AuthenticatedUser,
    session: DatabaseSession,
):
    return await repository(session, auth).create(OutcomeFeedback, body)


@router.get("/outcome-feedback", response_model=list[ArtResourceResponse])
async def list_outcome_feedback(
    auth: AuthenticatedUser,
    session: DatabaseSession,
    correlation_id: uuid.UUID | None = None,
    environment: str | None = None,
    limit: PageLimit = api_settings.api_default_limit,
):
    return await repository(session, auth).list(
        OutcomeFeedback,
        correlation_id=correlation_id,
        environment=environment,
        limit=limit,
    )


@router.post("/event-inbox", response_model=ArtResourceResponse, status_code=201)
async def create_event_inbox(
    body: EventInboxCreate,
    auth: AuthenticatedUser,
    session: DatabaseSession,
):
    return await repository(session, auth).create(ArtEventInbox, body)


@router.get("/event-inbox", response_model=list[ArtResourceResponse])
async def list_event_inbox(
    auth: AuthenticatedUser,
    session: DatabaseSession,
    correlation_id: uuid.UUID | None = None,
    environment: str | None = None,
    limit: PageLimit = api_settings.api_default_limit,
):
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
    return await repository(session, auth).create(ArtEventOutbox, body)


@router.get("/event-outbox", response_model=list[ArtResourceResponse])
async def list_event_outbox(
    auth: AuthenticatedUser,
    session: DatabaseSession,
    correlation_id: uuid.UUID | None = None,
    environment: str | None = None,
    limit: PageLimit = api_settings.api_default_limit,
):
    return await repository(session, auth).list(
        ArtEventOutbox,
        correlation_id=correlation_id,
        environment=environment,
        limit=limit,
    )


def _register_resource_read_route(
    resource: str,
    model: type[DeclarativeBase],
) -> None:
    async def read_resource(
        record_id: uuid.UUID,
        auth: AuthenticatedUser,
        session: DatabaseSession,
    ):
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
    return await repository(session, auth).correlation_trace(correlation_id)
