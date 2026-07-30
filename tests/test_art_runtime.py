"""Behavior tests for ART persistence and automatic lifecycle recording."""

import asyncio
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.art_lifecycle import LifecycleRecorder, correlation_uuid, event_environment
from app.art_models import (
    AgentDecisionJournal,
    AgentRun,
    AgentRunStep,
    ArtStatus,
    ExecutionIntent,
    FailureEvent,
    SelfHealProposal,
)
from app.art_repository import ArtRepository
from app.art_schemas import AgentRunCreate, LifecycleStateUpdate
from app.models import AuditLog, Event, Suggestion, SuggestionStatus
from app.security import Principal
from app.services import Candidate, FailureRoute


def make_event(**overrides) -> Event:
    values = {
        "id": uuid.uuid4(),
        "tenant_id": "acme",
        "external_id": "failure-42",
        "event_type": "ui.xpath.element_not_found",
        "source": "playwright",
        "severity": "error",
        "correlation_key": str(uuid.uuid4()),
        "payload": {
            "environment": "test",
            "test_name": "test_checkout",
            "failed_locator": "//button",
            "password": "must-not-be-stored",
            "payload_ref": "obs://failure-42",
        },
    }
    values.update(overrides)
    return Event(**values)


def test_correlation_and_environment_normalization():
    event = make_event(correlation_key="legacy-build-42")

    first = correlation_uuid(event)
    second = correlation_uuid(event)

    assert first == second
    assert event_environment(event) == "test"
    event.payload["environment"] = "unsupported"
    assert event_environment(event) == "dev"


def test_lifecycle_records_failure_steps_decision_and_proposal():
    session = SimpleNamespace(
        add=MagicMock(),
        add_all=MagicMock(),
        flush=AsyncMock(),
    )
    event = make_event()
    route = FailureRoute("ui", 0.93, ("explicit:ui",), ())
    recorder = LifecycleRecorder(session, event)

    asyncio.run(recorder.start(route))

    assert isinstance(recorder.failure, FailureEvent)
    assert isinstance(recorder.run, AgentRun)
    assert recorder.failure.failure_category == "UI"
    assert "password" not in recorder.failure.payload_summary
    assert recorder.run.status == ArtStatus.IN_PROGRESS.value

    suggestion = Suggestion(
        id=uuid.uuid4(),
        event_id=event.id,
        tenant_id=event.tenant_id,
        agent_type="ui",
        title="Replace stale locator",
        rationale="A unique test id is available.",
        proposed_changes={"locator": "[data-testid=checkout]", "rollback": "git://old"},
        evidence=[{"type": "screenshot"}],
        confidence=0.91,
        policy_result={"policies": ["ui-safe-change"]},
        status=SuggestionStatus.REVIEW,
    )
    candidate = Candidate(
        agent_type="ui",
        title=suggestion.title,
        rationale=suggestion.rationale,
        proposed_changes=suggestion.proposed_changes,
        base_confidence=0.9,
    )
    asyncio.run(recorder.record_candidate(candidate, suggestion))
    asyncio.run(recorder.complete())

    added_types = [type(call.args[0]) for call in session.add.call_args_list]
    assert AgentRunStep in added_types
    assert AgentDecisionJournal in added_types
    assert SelfHealProposal in added_types
    assert recorder.run.status == ArtStatus.SUCCESS.value
    assert recorder.run.completed_at is not None
    assert recorder.run.execution_time_ms >= 0


def test_lifecycle_records_failure_completion_and_ignores_unstarted_run():
    recorder = LifecycleRecorder(
        SimpleNamespace(add=MagicMock(), add_all=MagicMock(), flush=AsyncMock()),
        make_event(),
    )

    asyncio.run(
        recorder.record_candidate(
            Candidate("api", "title", "reason", {}, 0.5),
            SimpleNamespace(),
        )
    )
    asyncio.run(recorder.complete(failed=True, reason="boom"))
    assert recorder.run is None

    asyncio.run(recorder.start(FailureRoute("api", 0.8, ("endpoint",), ())))
    asyncio.run(recorder.complete(failed=True, reason="boom"))
    assert recorder.run.status == ArtStatus.FAILED.value
    assert recorder.run.failure_reason == "boom"


def test_repository_create_adds_tenant_and_audit_record():
    session = SimpleNamespace(
        add=MagicMock(),
        flush=AsyncMock(),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    )

    def assign_database_values(record):
        if isinstance(record, AgentRun):
            record.id = uuid.uuid4()
            record.created_at = datetime.now(UTC)

    session.add.side_effect = assign_database_values
    repository = ArtRepository(session, Principal("acme", "test-suite"))
    body = AgentRunCreate(
        correlation_id=uuid.uuid4(),
        environment="test",
        workflow_type="FAILURE_ANALYSIS",
    )

    response = asyncio.run(repository.create(AgentRun, body))

    assert response.tenant_id == "acme"
    assert response.status == "RECEIVED"
    assert any(isinstance(call.args[0], AuditLog) for call in session.add.call_args_list)
    session.commit.assert_awaited_once()


def test_repository_rejects_unknown_parent_and_ungoverned_state():
    missing_session = SimpleNamespace(scalar=AsyncMock(return_value=None))
    repository = ArtRepository(missing_session, Principal("acme", "tester"))

    with pytest.raises(HTTPException) as missing:
        asyncio.run(repository.get(AgentRun, uuid.uuid4()))
    assert missing.value.status_code == 404

    run = AgentRun(
        id=uuid.uuid4(),
        correlation_id=uuid.uuid4(),
        tenant_id="acme",
        environment="prod",
        workflow_type="FAILURE_ANALYSIS",
        status="RECEIVED",
    )
    governed_session = SimpleNamespace(scalar=AsyncMock(return_value=run))
    governed = ArtRepository(governed_session, Principal("acme", "tester"))

    intent = ExecutionIntent(
        id=uuid.uuid4(),
        correlation_id=uuid.uuid4(),
        tenant_id="acme",
        environment="prod",
        execution_target="suite",
        selected_tests=[],
        status="RECEIVED",
    )
    governed_session.scalar.return_value = intent
    with pytest.raises(HTTPException) as conflict:
        asyncio.run(
            governed.change_state(
                ExecutionIntent,
                intent.id,
                LifecycleStateUpdate(status="APPROVED"),
            )
        )
    assert conflict.value.status_code == 409


def test_repository_lists_changes_state_and_reads_correlation_trace():
    run = AgentRun(
        id=uuid.uuid4(),
        correlation_id=uuid.uuid4(),
        tenant_id="acme",
        environment="test",
        workflow_type="FAILURE_ANALYSIS",
        status="IN_PROGRESS",
        created_at=datetime.now(UTC),
    )
    scalar_result = MagicMock()
    scalar_result.all.return_value = [run]
    mapping_result = MagicMock()
    mapping_result.mappings.return_value.all.return_value = [
        {"correlation_id": run.correlation_id, "agent_run_status": "SUCCESS"}
    ]
    session = SimpleNamespace(
        scalars=AsyncMock(return_value=scalar_result),
        scalar=AsyncMock(return_value=run),
        execute=AsyncMock(return_value=mapping_result),
        add=MagicMock(),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    )
    repository = ArtRepository(session, Principal("acme", "tester"))

    listed = asyncio.run(
        repository.list(
            AgentRun,
            correlation_id=run.correlation_id,
            environment="test",
            limit=10,
        )
    )
    updated = asyncio.run(
        repository.change_state(
            AgentRun,
            run.id,
            LifecycleStateUpdate(status="SUCCESS"),
        )
    )
    trace = asyncio.run(repository.correlation_trace(run.correlation_id))

    assert [item.resource_id for item in listed] == [run.id]
    assert updated.status == "SUCCESS"
    assert trace["tenant_id"] == "acme"
    assert trace["records"][0]["agent_run_status"] == "SUCCESS"
