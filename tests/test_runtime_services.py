"""Tests for event processing and outbound webhook behavior."""

import asyncio
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import (
    Event,
    EventStatus,
    Suggestion,
    SuggestionStatus,
    WebhookDelivery,
    WebhookSubscription,
)
from app.processor import _create_suggestion, _queue_ready_webhooks, process_event
from app.services import Candidate, FailureRoute
from app.webhooks import cloud_event, deliver_due
from app.worker import run as run_worker


def processing_event() -> Event:
    return Event(
        id=uuid.uuid4(),
        tenant_id="acme",
        external_id="event-1",
        event_type="api.timeout",
        source="integration-tests",
        severity="error",
        correlation_key=str(uuid.uuid4()),
        payload={"endpoint": "/orders"},
        status=EventStatus.RECEIVED,
        attempts=0,
    )


def test_process_event_completes_and_records_candidate():
    event = processing_event()
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=event),
        add=MagicMock(),
    )
    lifecycle = SimpleNamespace(
        start=AsyncMock(),
        record_candidate=AsyncMock(),
        complete=AsyncMock(),
    )
    candidate = Candidate("api", "Fix timeout", "trace evidence", {"timeout": 10}, 0.8)
    suggestion = SimpleNamespace()

    with (
        patch("app.processor.LifecycleRecorder", return_value=lifecycle),
        patch("app.processor.KnowledgeService.search", new=AsyncMock(return_value=[])),
        patch(
            "app.processor.routed_agents",
            return_value=(
                FailureRoute("api", 0.9, ("endpoint",), ()),
                [SimpleNamespace(suggest=AsyncMock(return_value=candidate))],
            ),
        ),
        patch("app.processor.AIService.enrich", new=AsyncMock(return_value=candidate)),
        patch("app.processor._create_suggestion", new=AsyncMock(return_value=suggestion)),
        patch("app.processor._queue_ready_webhooks", new=AsyncMock()) as queue,
    ):
        asyncio.run(process_event(session, event.id))

    assert event.status == EventStatus.COMPLETED
    assert event.attempts == 1
    lifecycle.start.assert_awaited_once()
    lifecycle.record_candidate.assert_awaited_once()
    lifecycle.complete.assert_awaited_once_with()
    queue.assert_awaited_once()


def test_process_event_marks_failure_and_reraises():
    event = processing_event()
    session = SimpleNamespace(scalar=AsyncMock(return_value=event))
    lifecycle = SimpleNamespace(start=AsyncMock(), complete=AsyncMock())

    with (
        patch("app.processor.LifecycleRecorder", return_value=lifecycle),
        patch(
            "app.processor.KnowledgeService.search",
            new=AsyncMock(side_effect=RuntimeError("knowledge unavailable")),
        ),
    ):
        try:
            asyncio.run(process_event(session, event.id))
        except RuntimeError:
            pass
        else:
            raise AssertionError("processor must re-raise unexpected failures")

    assert event.status == EventStatus.FAILED
    assert event.error == "knowledge unavailable"
    lifecycle.complete.assert_awaited_once_with(
        failed=True,
        reason="knowledge unavailable",
    )


def test_forced_reanalysis_marks_candidate_as_alternative_negative_learning():
    event = processing_event()
    event.status = EventStatus.COMPLETED
    event.payload = {
        **event.payload,
        "art_failed_suggestions": [{"suggestion_id": "failed-1", "title": "Increase timeout"}],
    }
    session = SimpleNamespace(scalar=AsyncMock(return_value=event), add=MagicMock())
    lifecycle = SimpleNamespace(
        start=AsyncMock(), record_candidate=AsyncMock(), complete=AsyncMock()
    )
    candidate = Candidate("api", "Fix timeout", "trace evidence", {"timeout": 10}, 0.9)
    created = AsyncMock(return_value=SimpleNamespace())

    with (
        patch("app.processor.LifecycleRecorder", return_value=lifecycle),
        patch("app.processor.KnowledgeService.search", new=AsyncMock(return_value=[])),
        patch(
            "app.processor.routed_agents",
            return_value=(
                FailureRoute("api", 0.9, ("endpoint",), ()),
                [SimpleNamespace(suggest=AsyncMock(return_value=candidate))],
            ),
        ),
        patch("app.processor.AIService.enrich", new=AsyncMock(return_value=candidate)),
        patch("app.processor._create_suggestion", new=created),
        patch("app.processor._queue_ready_webhooks", new=AsyncMock()),
    ):
        asyncio.run(process_event(session, event.id, force=True))

    alternative = created.await_args.args[2]
    assert alternative.title.startswith("Alternative investigation:")
    assert alternative.proposed_changes["action"] == "investigate_alternative_remediation"
    assert alternative.proposed_changes["must_not_repeat_suggestion_ids"] == ["failed-1"]
    assert alternative.base_confidence == 0.79


def test_create_suggestion_applies_policy_and_audits():
    event = processing_event()
    session = SimpleNamespace(add=MagicMock(), flush=AsyncMock())
    candidate = Candidate(
        "api",
        "Fix timeout",
        "Trace evidence",
        {"timeout": 10},
        0.8,
    )

    with patch(
        "app.processor.PolicyEngine.evaluate",
        new=AsyncMock(
            return_value=(
                SuggestionStatus.READY,
                {"allowed": True},
                0.9,
            )
        ),
    ):
        suggestion = asyncio.run(_create_suggestion(session, event, candidate, [{"type": "trace"}]))

    assert suggestion.status == SuggestionStatus.READY
    assert suggestion.confidence == 0.9
    assert len(session.add.call_args_list) == 2
    session.flush.assert_awaited_once()


def test_ready_suggestion_queues_only_matching_active_subscriptions():
    event = processing_event()
    suggestion = SimpleNamespace(
        id=uuid.uuid4(),
        status=SuggestionStatus.READY,
    )
    subscriptions = [
        WebhookSubscription(
            id=uuid.uuid4(),
            tenant_id="acme",
            name="matching",
            callback_url="https://example.test/one",
            event_types=["suggestion.ready"],
            active=True,
        ),
        WebhookSubscription(
            id=uuid.uuid4(),
            tenant_id="acme",
            name="other",
            callback_url="https://example.test/two",
            event_types=["other.event"],
            active=True,
        ),
    ]
    scalar_result = MagicMock()
    scalar_result.all.return_value = subscriptions
    session = SimpleNamespace(
        scalars=AsyncMock(return_value=scalar_result),
        add=MagicMock(),
    )

    asyncio.run(_queue_ready_webhooks(session, event, suggestion))
    assert session.add.call_count == 1

    suggestion.status = SuggestionStatus.REVIEW
    asyncio.run(_queue_ready_webhooks(session, event, suggestion))
    assert session.add.call_count == 1


def webhook_records():
    suggestion = Suggestion(
        id=uuid.uuid4(),
        event_id=uuid.uuid4(),
        tenant_id="acme",
        agent_type="api",
        title="Fix timeout",
        rationale="Trace confirms a timeout.",
        proposed_changes={"timeout": 10},
        evidence=[],
        confidence=0.88,
        policy_result={"allowed": True},
        status=SuggestionStatus.READY,
        created_at=datetime.now(UTC),
    )
    subscription = WebhookSubscription(
        id=uuid.uuid4(),
        tenant_id="acme",
        name="consumer",
        callback_url="https://example.test/hooks",
        event_types=["suggestion.ready"],
        secret="test-secret",
        active=True,
    )
    delivery = WebhookDelivery(
        id=uuid.uuid4(),
        tenant_id="acme",
        subscription_id=subscription.id,
        suggestion_id=suggestion.id,
        status="pending",
        attempts=0,
        next_attempt_at=datetime.now(UTC),
    )
    return suggestion, subscription, delivery


def test_cloud_event_contains_traceable_suggestion_data():
    suggestion, _, _ = webhook_records()

    event = cloud_event(suggestion)

    assert event["type"] == "suggestion.ready"
    assert event["tenantid"] == "acme"
    assert event["data"]["suggestion_id"] == str(suggestion.id)


def test_webhook_delivery_success_and_retry():
    suggestion, subscription, delivery = webhook_records()
    scalars = MagicMock()
    scalars.all.return_value = [delivery]
    session = SimpleNamespace(
        scalars=AsyncMock(return_value=scalars),
        get=AsyncMock(side_effect=[subscription, suggestion]),
        add=MagicMock(),
    )
    response = SimpleNamespace(status_code=202, raise_for_status=MagicMock())
    client = AsyncMock()
    client.post.return_value = response
    context = AsyncMock()
    context.__aenter__.return_value = client

    with patch("app.webhooks.httpx.AsyncClient", return_value=context):
        assert asyncio.run(deliver_due(session)) == 1

    assert delivery.status == "delivered"
    assert delivery.response_status == 202
    assert delivery.attempts == 1

    delivery.status = "retry"
    delivery.attempts = 0
    delivery.response_status = None
    session.get.side_effect = [subscription, suggestion]
    failing_client = AsyncMock()
    failing_client.post.side_effect = RuntimeError("connection refused")
    failing_context = AsyncMock()
    failing_context.__aenter__.return_value = failing_client

    with patch("app.webhooks.httpx.AsyncClient", return_value=failing_context):
        assert asyncio.run(deliver_due(session)) == 1

    assert delivery.status == "retry"
    assert delivery.last_error == "connection refused"


def test_webhook_cancels_delivery_with_missing_subscription():
    _, _, delivery = webhook_records()
    scalars = MagicMock()
    scalars.all.return_value = [delivery]
    session = SimpleNamespace(
        scalars=AsyncMock(return_value=scalars),
        get=AsyncMock(return_value=None),
        add=MagicMock(),
    )

    assert asyncio.run(deliver_due(session)) == 1
    assert delivery.status == "cancelled"


def test_worker_processes_one_idle_iteration():
    scalar_result = MagicMock()
    scalar_result.all.return_value = []
    session = SimpleNamespace(
        scalars=AsyncMock(return_value=scalar_result),
        commit=AsyncMock(),
    )
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    settings = SimpleNamespace(
        external_postgres_enabled=False,
        worker_poll_seconds=0.01,
    )

    with (
        patch("app.worker.get_settings", return_value=settings),
        patch("app.worker.SessionLocal", return_value=session_context),
        patch("app.worker.deliver_due", new=AsyncMock(return_value=0)),
        patch(
            "app.worker.asyncio.sleep",
            new=AsyncMock(side_effect=asyncio.CancelledError),
        ),
    ):
        try:
            asyncio.run(run_worker())
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("the test cancellation must stop the worker loop")

    session.commit.assert_awaited_once()
