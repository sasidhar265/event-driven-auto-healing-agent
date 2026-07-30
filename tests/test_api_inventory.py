"""Protect the API contracts used by UI, integrations, and ART requirements."""

from app.main import app, create_application

CORE_PATHS = {
    "/v1/overview",
    "/v1/events",
    "/v1/events/{event_id}",
    "/v1/events/{event_id}/trace",
    "/v1/suggestions",
    "/v1/suggestions/{suggestion_id}/decision",
    "/v1/audit",
}

INTERNAL_PATHS = {
    "/v1/internal/references",
    "/v1/internal/policies",
    "/v1/internal/knowledge",
}

INTEGRATION_PATHS = {
    "/v1/events/cloudevents",
    "/v1/subscriptions",
    "/v1/subscriptions/{subscription_id}",
    "/v1/deliveries",
    "/v1/deliveries/{delivery_id}/retry",
}


def test_core_api_contract_is_registered():
    paths = app.openapi()["paths"]

    for path in CORE_PATHS:
        assert path in paths


def test_audit_contract_exposes_database_filter_parameters():
    audit_operation = app.openapi()["paths"]["/v1/audit"]["get"]
    parameter_names = {parameter["name"] for parameter in audit_operation["parameters"]}

    assert {"environment", "from_time", "to_time", "correlation_id"} <= parameter_names


def test_operation_ids_are_unique():
    operations = []
    for path, methods in app.openapi()["paths"].items():
        for method, operation in methods.items():
            if method in {"get", "post", "patch", "put", "delete"}:
                operations.append((operation["operationId"], method, path))

    identifiers = [operation_id for operation_id, _, _ in operations]
    assert len(identifiers) == len(set(identifiers))


def test_operations_profile_hides_integration_and_admin_routes():
    paths = app.openapi()["paths"]

    assert INTEGRATION_PATHS.isdisjoint(paths)
    assert INTERNAL_PATHS.isdisjoint(paths)
    assert not any(path.startswith("/v1/art/") for path in paths)


def test_full_profile_keeps_every_optional_contract_available():
    paths = create_application("full").openapi()["paths"]

    assert INTEGRATION_PATHS.issubset(paths)
    assert INTERNAL_PATHS.issubset(paths)
    assert "/v1/art/failure-events" in paths
