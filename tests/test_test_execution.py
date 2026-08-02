"""Safety checks for accepted-suggestion test reruns."""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import Event, Outbox, RemediationReference, Suggestion, SuggestionStatus
from app.test_execution import (
    _queue_bounded_reanalysis,
    execute_accepted_suggestion,
    validated_test_target,
)


def test_accepts_existing_repository_test_target():
    assert (
        validated_test_target(
            {
                "test_file": "tests/test_runtime_intelligence.py",
                "test_name": "test_recovery_requires_metrics_and_reports_partial_improvement",
            }
        )
        == "tests/test_runtime_intelligence.py::test_recovery_requires_metrics_and_reports_partial_improvement"
    )


def test_rejects_missing_traversal_and_unsafe_test_targets():
    assert validated_test_target({}) is None
    assert validated_test_target({"test_file": "app/main.py"}) is None
    assert validated_test_target({"test_file": "tests/../app/main.py"}) is None
    assert (
        validated_test_target(
            {
                "test_file": "tests/test_runtime_intelligence.py",
                "test_name": "test_ok; touch /tmp/unsafe",
            }
        )
        is None
    )


def test_failed_rerun_invalidates_reference_and_queues_bounded_reanalysis():
    event = Event(
        id=uuid.uuid4(),
        tenant_id="acme",
        external_id="failure-1",
        event_type="application.logic.exception",
        source="tests",
        severity="error",
        correlation_key="failure-1",
        payload={
            "test_file": "tests/test_runtime_intelligence.py",
            "test_name": "test_recovery_requires_metrics_and_reports_partial_improvement",
        },
    )
    suggestion = Suggestion(
        id=uuid.uuid4(),
        event_id=event.id,
        tenant_id="acme",
        agent_type="logic",
        title="Fix invariant",
        rationale="Observed failure",
        proposed_changes={"action": "fix"},
        evidence=[],
        confidence=0.9,
        policy_result={},
        status=SuggestionStatus.ACCEPTED,
    )
    reference = RemediationReference(
        suggestion_id=suggestion.id,
        event_id=event.id,
        tenant_id="acme",
        event_type=event.event_type,
        severity=event.severity,
        fingerprint="fingerprint",
        agent_type="logic",
        title=suggestion.title,
        rationale=suggestion.rationale,
        proposed_changes=suggestion.proposed_changes,
        evidence=[],
        confidence=0.9,
        outcome="accepted",
        decision_reason="approved",
        active=True,
    )
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[suggestion, event, reference]),
        add=MagicMock(),
        flush=AsyncMock(),
    )
    failed = {"status": "FAILED", "return_code": 1, "output": "same assertion failed"}

    with patch("app.test_execution._run_pytest", new=AsyncMock(return_value=failed)):
        asyncio.run(execute_accepted_suggestion(session, suggestion.id))

    records = [call.args[0] for call in session.add.call_args_list]
    assert reference.active is False
    assert reference.outcome == "test_failed"
    assert event.payload["art_reanalysis_attempts"] == 1
    queued = next(record for record in records if isinstance(record, Outbox))
    assert queued.topic == "event.reanalysis.requested"
    assert any(
        record.action == "event.reanalysis_queued"
        for record in records
        if hasattr(record, "action")
    )


def test_reanalysis_escalates_after_attempt_limit_without_another_job():
    event = Event(
        id=uuid.uuid4(),
        tenant_id="acme",
        external_id="failure-limit",
        event_type="api.timeout",
        source="tests",
        severity="error",
        correlation_key="failure-limit",
        payload={"art_reanalysis_attempts": 2},
    )
    suggestion = SimpleNamespace(id=uuid.uuid4(), title="Failed twice", agent_type="api")
    session = SimpleNamespace(add=MagicMock())

    asyncio.run(
        _queue_bounded_reanalysis(
            session, event, suggestion, "tests/test_api.py::test_timeout", "failed"
        )
    )

    records = [call.args[0] for call in session.add.call_args_list]
    assert not any(isinstance(record, Outbox) for record in records)
    escalation = next(record for record in records if hasattr(record, "action"))
    assert escalation.action == "event.reanalysis_escalated"
    assert escalation.details["human_investigation_required"] is True
