import asyncio
from types import SimpleNamespace

import pytest

from app.services import routed_agents, specialist_agents


def test_api_agent_recognizes_timeout():
    event = SimpleNamespace(event_type="api.timeout", payload={"endpoint": "/orders"}, severity="error")
    async def collect():
        return [await agent.suggest(event, []) for agent in specialist_agents()]
    candidates = asyncio.run(collect())
    api = next(item for item in candidates if item and item.agent_type == "api")
    assert api.proposed_changes["action"] == "propose_api_change"
    assert api.base_confidence < 0.6
    assert "source_file or test_file" in api.proposed_changes["required_evidence"]


def test_irrelevant_agent_abstains():
    event = SimpleNamespace(
        event_type="unclassified.signal", payload={"opaque_code": "x-90"}, severity="warning"
    )
    async def collect():
        return [await agent.suggest(event, []) for agent in specialist_agents()]
    candidates = asyncio.run(collect())
    assert all(candidate is None for candidate in candidates)


def test_xpath_agent_prefers_unique_test_id():
    event = SimpleNamespace(
        event_type="ui.xpath.element_not_found", severity="error",
        payload={
            "failed_locator": {"strategy": "xpath", "value": "//button[@id='submit-order']"},
            "test_file": "tests/ui/test_checkout.py", "test_name": "test_submit_order",
            "dom_candidates": [{"tag": "button", "text": "Submit order", "attributes": {"data-testid": "submit-order"}}],
        },
    )
    candidate = asyncio.run(specialist_agents()[0].suggest(event, [{"title": "locator standard"}]))
    assert candidate.proposed_changes["recommended_locator"] == {
        "strategy": "css-selector", "value": '[data-testid="submit-order"]'
    }
    assert candidate.base_confidence >= 0.9


def test_router_sends_xpath_failure_only_to_xpath_specialist():
    event = SimpleNamespace(
        event_type="test.failed", source="playwright", severity="error",
        payload={
            "failure_category": "ui",
            "failed_locator": {"strategy": "xpath", "value": "//button"},
            "dom_candidates": [{"attributes": {"data-testid": "submit-order"}}],
            "test_file": "tests/ui/test_checkout.py",
            "test_name": "test_submit_order",
        },
    )
    route, agents = routed_agents(event)
    assert route.category == "ui"
    assert route.confidence >= 0.8
    assert len(agents) == 1
    assert type(agents[0]).__name__ == "XPathInvestigationAgent"


def test_router_sends_structured_api_failure_to_api_agent():
    event = SimpleNamespace(
        event_type="test.failed", source="integration-tests", severity="error",
        payload={
            "endpoint": "/orders", "http_method": "POST", "status_code": 500,
            "exception_type": "ReadTimeout", "trace_id": "trace-42",
            "source_file": "app/orders.py", "method_name": "create_order",
        },
    )
    route, agents = routed_agents(event)
    assert route.category == "api"
    assert [agent.agent_type for agent in agents] == ["api"]
    candidate = asyncio.run(agents[0].suggest(event, []))
    assert candidate.proposed_changes["target"] == {
        "file": "app/orders.py", "method": "create_order"
    }
    assert candidate.base_confidence >= 0.6


def test_ambiguous_failure_routes_to_evidence_collection():
    event = SimpleNamespace(
        event_type="test.failed", source="ci", severity="error",
        payload={"message": "request state failed"},
    )
    route, agents = routed_agents(event)
    assert route.ambiguous
    assert [agent.agent_type for agent in agents] == ["investigation"]
    candidate = asyncio.run(agents[0].suggest(event, []))
    assert candidate.proposed_changes["action"] == "collect_failure_evidence"
    assert candidate.base_confidence < 0.6


@pytest.mark.parametrize(
    ("category", "payload", "expected_action"),
    [
        (
            "database",
            {
                "database_system": "postgres", "sql_state": "40P01",
                "query": "UPDATE orders", "source_file": "app/orders.py",
                "method_name": "update_order",
            },
            "propose_database_change",
        ),
        (
            "infrastructure",
            {
                "cluster": "prod-eu", "namespace": "orders", "pod": "orders-7",
                "resource_metrics": {"memory_percent": 99},
                "manifest_file": "deploy/orders.yaml", "resource_name": "orders",
            },
            "propose_infrastructure_change",
        ),
        (
            "dependency",
            {
                "dependency_name": "payments", "dependency_endpoint": "/authorize",
                "upstream_status": 503, "config_file": "config/resilience.yaml",
                "trace_id": "trace-dependency",
            },
            "propose_dependency_change",
        ),
        (
            "security",
            {
                "security_control": "authorization", "principal": "orders-worker",
                "permission": "payments.authorize", "policy_file": "policy/orders.rego",
            },
            "propose_security_change",
        ),
        (
            "performance",
            {
                "baseline_ms": 180, "observed_ms": 1450, "p95_ms": 1700,
                "profile": "orders-create", "source_file": "app/orders.py",
                "method_name": "create_order",
            },
            "propose_performance_change",
        ),
    ],
)
def test_extended_failure_categories_route_to_specialist(category, payload, expected_action):
    event = SimpleNamespace(
        event_type=f"{category}.test.failed", source="ci", severity="error",
        payload={"failure_category": category, **payload},
    )
    route, agents = routed_agents(event)
    assert route.category == category
    assert not route.ambiguous
    assert [agent.agent_type for agent in agents] == [category]
    candidate = asyncio.run(agents[0].suggest(event, []))
    assert candidate.proposed_changes["action"] == expected_action
    assert candidate.proposed_changes["target"]["file"]
