"""Cross-sector runtime intelligence behavior."""

from app.services.runtime_intelligence import (
    evaluate_recovery,
    incident_fingerprint,
    normalize_incident,
    plan_playbook,
    score_business_impact,
)


def context(**payload):
    return normalize_incident(
        event_type="unclassified.failure",
        source="otel://collector",
        severity="critical",
        payload=payload,
    )


def test_normalizes_otel_and_vendor_fields_and_redacts_sensitive_values():
    normalized = context(
        **{
            "service.name": "payments",
            "exception.type": "TimeoutError",
            "traceId": "trace-42",
            "affected_users": "1200",
            "password": "must-not-leak",
            "data_classification": "restricted",
        }
    )

    assert normalized["service"] == "payments"
    assert normalized["exception"]["type"] == "TimeoutError"
    assert normalized["trace_id"] == "trace-42"
    assert normalized["business"]["affected_users"] == 1200
    assert "must-not-leak" not in str(normalized)


def test_fingerprint_ignores_volatile_message_but_separates_services():
    first = context(service="orders", exception_type="TimeoutError", message="one")
    second = context(service="orders", exception_type="TimeoutError", message="two")
    other = context(service="payments", exception_type="TimeoutError", message="one")

    assert incident_fingerprint(first) == incident_fingerprint(second)
    assert incident_fingerprint(first) != incident_fingerprint(other)


def test_business_impact_produces_explainable_priority():
    normalized = context(
        service="payments",
        business_criticality="critical",
        affected_users=5000,
        revenue_exposure=200000,
    )
    impact = score_business_impact(normalized)

    assert impact == {
        "score": 100,
        "priority": "P1",
        "factors": [
            {"signal": "technical_severity", "points": 45},
            {"signal": "business_criticality", "points": 30},
            {"signal": "affected_users", "points": 20},
            {"signal": "revenue_exposure", "points": 15},
        ],
    }


def test_playbook_is_dry_run_and_requires_resource_identity():
    plan = plan_playbook("pod is OOMKilled", context(service="checkout"))

    assert plan["id"] == "restart-stateless-instance"
    assert plan["mode"] == "dry-run"
    assert plan["execution_authorized"] is False
    assert plan["preconditions"]["passed"] is True


def test_generic_message_field_does_not_select_replay_playbook():
    normalized = context(
        component="payments-authorization",
        message="403 forbidden: required permission is absent",
    )
    assert (
        plan_playbook(
            "security.authorization.forbidden 403 forbidden: required permission is absent",
            normalized,
        )
        is None
    )


def test_recovery_requires_metrics_and_reports_partial_improvement():
    assert evaluate_recovery({}, {})["status"] == "insufficient_evidence"
    result = evaluate_recovery(
        {"error_rate": 0.2, "latency_ms": 500},
        {"error_rate": 0.01, "latency_ms": 600},
    )
    assert result["status"] == "partially_recovered"
    assert result["recovered"] is False
