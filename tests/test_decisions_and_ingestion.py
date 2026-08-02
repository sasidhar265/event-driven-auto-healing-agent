"""Tests for event ingestion and remediation learning decisions."""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.decisions import event_fingerprint, record_suggestion_decision
from app.ingestion import cloud_event_to_event, persist_cloud_event, persist_event
from app.models import (
    AuditLog,
    Event,
    Outbox,
    RemediationReference,
    Suggestion,
    SuggestionDecision,
    SuggestionStatus,
)
from app.schemas import CloudEventCreate, DecisionCreate, EventCreate
from app.security import Principal


def event_and_suggestion():
    event = Event(
        id=uuid.uuid4(),
        tenant_id="acme",
        external_id="event-42",
        event_type="api.timeout",
        source="tests",
        severity="error",
        correlation_key="build-42",
        payload={"endpoint": "/orders", "timeout": 5},
    )
    suggestion = Suggestion(
        id=uuid.uuid4(),
        event_id=event.id,
        tenant_id="acme",
        agent_type="api",
        title="Increase timeout",
        rationale="Observed latency exceeds the configured timeout.",
        proposed_changes={"timeout": 10},
        evidence=[],
        confidence=0.85,
        policy_result={},
        status=SuggestionStatus.REVIEW,
    )
    return event, suggestion


def test_event_fingerprint_is_stable_and_payload_sensitive():
    event, _ = event_and_suggestion()
    same = event_and_suggestion()[0]
    same.event_type = event.event_type
    same.payload = event.payload

    assert event_fingerprint(event) == event_fingerprint(same)
    same.payload = {"endpoint": "/payments"}
    assert event_fingerprint(event) != event_fingerprint(same)


def test_accepting_suggestion_creates_decision_reference_and_audit():
    event, suggestion = event_and_suggestion()
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[None, None]),
        add=MagicMock(),
    )
    request = DecisionCreate(decision="accepted", reason="Validated in test")

    asyncio.run(
        record_suggestion_decision(
            session,
            suggestion,
            event,
            request,
            Principal("acme", "reviewer"),
        )
    )

    records = [call.args[0] for call in session.add.call_args_list]
    assert suggestion.status == SuggestionStatus.ACCEPTED
    assert any(isinstance(record, SuggestionDecision) for record in records)
    rerun = next(record for record in records if isinstance(record, Outbox))
    assert rerun.topic == "test.rerun.requested"
    assert rerun.aggregate_id == suggestion.id
    reference = next(record for record in records if isinstance(record, RemediationReference))
    assert reference.active is True
    assert reference.fingerprint == event_fingerprint(event)
    assert any(isinstance(record, AuditLog) for record in records)


def test_rejecting_suggestion_updates_existing_learning_records():
    event, suggestion = event_and_suggestion()
    decision = SuggestionDecision(
        suggestion_id=suggestion.id,
        tenant_id="acme",
        decision="accepted",
        reason="old",
        actor="old-reviewer",
    )
    reference = RemediationReference(
        suggestion_id=suggestion.id,
        event_id=event.id,
        tenant_id="acme",
        event_type=event.event_type,
        severity=event.severity,
        fingerprint="old",
        agent_type=suggestion.agent_type,
        title=suggestion.title,
        rationale=suggestion.rationale,
        proposed_changes={},
        evidence=[],
        confidence=0.5,
        outcome="accepted",
        decision_reason="old",
        active=True,
    )
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[decision, reference]),
        add=MagicMock(),
    )

    asyncio.run(
        record_suggestion_decision(
            session,
            suggestion,
            event,
            DecisionCreate(decision="rejected", reason="Unsafe change"),
            Principal("acme", "security-reviewer"),
        )
    )

    assert suggestion.status == SuggestionStatus.REJECTED
    assert decision.decision == "rejected"
    assert decision.actor == "security-reviewer"
    assert reference.active is False
    assert reference.decision_reason == "Unsafe change"


def test_persist_event_is_idempotent_and_creates_outbox_work():
    body = EventCreate(
        external_id="event-1",
        event_type="api.timeout",
        source="tests",
        severity="error",
        correlation_key="build-1",
        payload={"endpoint": "/orders"},
    )
    existing = Event(tenant_id="acme", **body.model_dump())
    existing_session = SimpleNamespace(scalar=AsyncMock(return_value=existing))
    assert (
        asyncio.run(persist_event(body, Principal("acme", "tester"), existing_session)) is existing
    )

    session = SimpleNamespace(
        scalar=AsyncMock(return_value=None),
        add=MagicMock(),
        flush=AsyncMock(),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    )

    stored = asyncio.run(persist_event(body, Principal("acme", "tester"), session))

    assert stored.tenant_id == "acme"
    records = [call.args[0] for call in session.add.call_args_list]
    created_event = next(record for record in records if isinstance(record, Event))
    assert created_event.payload["art_context"]["event_type"] == "api.timeout"
    assert created_event.payload["art_incident_fingerprint"]
    assert created_event.payload["art_business_impact"]["priority"] == "P3"
    assert any(isinstance(record, Outbox) for record in records)
    assert any(isinstance(record, AuditLog) for record in records)
    session.commit.assert_awaited_once()


def test_cloud_event_conversion_and_persistence():
    raw = {
        "specversion": "1.0",
        "id": "cloud-42",
        "source": "ci://orders",
        "type": "api.timeout",
        "subject": "build-42",
        "tenantid": "acme",
        "severity": "error",
        "data": {"endpoint": "/orders"},
    }
    converted = cloud_event_to_event(CloudEventCreate.model_validate(raw))
    assert converted.correlation_key == "build-42"
    assert converted.payload["cloudevent"]["specversion"] == "1.0"

    existing = Event(tenant_id="acme", **converted.model_dump())
    session = SimpleNamespace(scalar=AsyncMock(return_value=existing))
    stored = asyncio.run(persist_cloud_event(raw, Principal("acme", "backbone"), session))
    assert stored is existing
