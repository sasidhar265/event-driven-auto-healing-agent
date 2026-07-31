import uuid

import pytest
from pydantic import ValidationError

from app.art_schemas import ExecutionIntentCreate, FailureEventCreate
from app.main import create_application

app = create_application("full")

PUBLIC_ART_COLLECTIONS = {
    "failure-events",
    "agent-runs",
    "impact-assessments",
    "execution-intents",
}


def test_openapi_exposes_only_requirement_facing_art_resources():
    paths = app.openapi()["paths"]
    art_paths = {path for path in paths if path.startswith("/v1/art/")}

    for resource in PUBLIC_ART_COLLECTIONS:
        path = paths[f"/v1/art/{resource}"]
        assert "post" in path
        assert "get" in path
    assert art_paths == {f"/v1/art/{resource}" for resource in PUBLIC_ART_COLLECTIONS}


def test_failure_event_requires_enterprise_context():
    with pytest.raises(ValidationError):
        FailureEventCreate(
            source_system="playwright",
            failure_category="UI",
            severity="HIGH",
        )


def test_large_failure_payload_requires_external_reference():
    with pytest.raises(ValidationError, match="payload_ref"):
        FailureEventCreate(
            correlation_id=uuid.uuid4(),
            environment="test",
            source_system="api-tests",
            payload_summary={"body": "x" * 17_000},
        )


def test_executed_intent_requires_governance_decision():
    with pytest.raises(ValidationError, match="policy_decision_id"):
        ExecutionIntentCreate(
            correlation_id=uuid.uuid4(),
            environment="prod",
            execution_target="regression-suite",
            selected_tests=["test_checkout"],
            status="EXECUTED",
        )


def test_governed_execution_intent_is_valid():
    item = ExecutionIntentCreate(
        correlation_id=uuid.uuid4(),
        environment="prod",
        execution_target="regression-suite",
        selected_tests=["test_checkout"],
        sequence_plan=[{"sequence": 1, "test": "test_checkout"}],
        status="APPROVED",
        policy_decision_id=uuid.uuid4(),
        policy_version="gov-42",
        approval_required=True,
        approval_status="PENDING",
    )

    assert item.environment == "prod"
    assert item.policy_version == "gov-42"
