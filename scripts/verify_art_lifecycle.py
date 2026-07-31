"""Exercise every ART lifecycle API against a running local server."""

import os
import sys
import uuid

import httpx

BASE_URL = os.getenv("ART_VERIFY_BASE_URL", "http://127.0.0.1:8000")
HEADERS = {
    "X-API-Key": os.getenv("ART_VERIFY_API_KEY", "change-me"),
    "X-Tenant-Id": os.getenv("ART_VERIFY_TENANT", "art-verification"),
    "X-Actor": os.getenv("ART_VERIFY_ACTOR", "lifecycle-verifier"),
}


def create(client: httpx.Client, resource: str, payload: dict) -> dict:
    response = client.post(f"/v1/art/{resource}", json=payload)
    response.raise_for_status()
    record = response.json()
    print(f"{resource}: {record['status']} ({record['resource_id']})")
    return record


def main() -> int:
    correlation_id = str(uuid.uuid4())
    common = {"correlation_id": correlation_id, "environment": "test"}

    timeout = float(os.getenv("ART_VERIFY_TIMEOUT_SECONDS", "15"))
    with httpx.Client(base_url=BASE_URL, headers=HEADERS, timeout=timeout) as client:
        failure = create(
            client,
            "failure-events",
            {
                **common,
                "source_system": "verification-suite",
                "failure_category": "API",
                "severity": "HIGH",
                "failure_subtype": "api.timeout",
                "payload_summary": {"endpoint": "/orders", "timeout_ms": 5000},
                "payload_ref": "obs://verification/failure-payload",
            },
        )
        run = create(
            client,
            "agent-runs",
            {
                **common,
                "workflow_type": "FAILURE_ANALYSIS",
                "trigger_event_type": "api.timeout",
                "status": "IN_PROGRESS",
                "created_by": "lifecycle-verifier",
            },
        )
        step = create(
            client,
            "agent-run-steps",
            {
                **common,
                "agent_run_id": run["resource_id"],
                "agent_name": "api",
                "step_name": "diagnose_timeout",
                "step_sequence": 1,
                "status": "SUCCESS",
                "confidence_score": 0.91,
                "confidence_reason": "Trace and endpoint evidence agree.",
            },
        )
        create(
            client,
            "decision-journals",
            {
                **common,
                "agent_run_id": run["resource_id"],
                "agent_step_id": step["resource_id"],
                "decision_type": "IMPACT_ASSESSMENT",
                "decision_summary": "Orders API latency affects checkout.",
                "confidence_score": 0.91,
                "evidence_refs": ["obs://verification/trace"],
            },
        )
        impact = create(
            client,
            "impact-assessments",
            {
                **common,
                "agent_run_id": run["resource_id"],
                "impact_source": "failure",
                "component_name": "orders-api",
                "component_type": "service",
                "service_name": "orders",
                "impact_level": "HIGH",
                "risk_score": 0.82,
                "confidence_score": 0.91,
                "affected_test_tags": ["orders", "checkout"],
            },
        )
        create(
            client,
            "impact-dependencies",
            {
                **common,
                "impact_assessment_id": impact["resource_id"],
                "dependent_component_name": "checkout-ui",
                "dependency_direction": "DOWNSTREAM",
                "dependency_type": "HTTP",
                "dependency_confidence": 0.88,
            },
        )
        selection = create(
            client,
            "test-selection-decisions",
            {
                **common,
                "agent_run_id": run["resource_id"],
                "selection_strategy": "RISK_BASED",
                "selected_tests": ["test_create_order", "test_checkout"],
                "skipped_tests": ["test_profile"],
                "mandatory_tests": ["test_create_order"],
                "risk_coverage": 0.94,
                "confidence_score": 0.90,
                "policy_decision_id": str(uuid.uuid4()),
                "policy_version": "gov-verification-1",
            },
        )
        policy_id = str(uuid.uuid4())
        intent = create(
            client,
            "execution-intents",
            {
                **common,
                "agent_run_id": run["resource_id"],
                "test_selection_decision_id": selection["resource_id"],
                "execution_target": "local-regression",
                "selected_tests": ["test_create_order", "test_checkout"],
                "sequence_plan": [
                    {"sequence": 1, "test": "test_create_order"},
                    {"sequence": 2, "test": "test_checkout"},
                ],
                "status": "APPROVED",
                "policy_decision_id": policy_id,
                "policy_version": "gov-verification-1",
            },
        )
        result = create(
            client,
            "execution-result-refs",
            {
                **common,
                "execution_intent_id": intent["resource_id"],
                "status": "SUCCESS",
                "passed_count": 2,
                "failed_count": 0,
                "skipped_count": 0,
                "result_ref": "obs://verification/result",
            },
        )
        create(
            client,
            "self-heal-proposals",
            {
                **common,
                "agent_run_id": run["resource_id"],
                "failure_event_id": failure["resource_id"],
                "proposal_type": "CONFIG_DEPENDENCY",
                "proposal_summary": "Review downstream timeout budget.",
                "suggested_change": {"file": "config/orders.yaml", "timeout_ms": 6000},
                "confidence_score": 0.83,
                "approval_required": True,
                "approval_status": "PENDING",
                "rollback_ref": "git://config/orders.yaml@previous",
                "policy_decision_id": policy_id,
            },
        )
        create(
            client,
            "outcome-feedback",
            {
                **common,
                "agent_run_id": run["resource_id"],
                "execution_intent_id": intent["resource_id"],
                "execution_result_ref_id": result["resource_id"],
                "feedback_type": "TEST_EFFECTIVENESS",
                "feedback_summary": "Selected tests validated the affected path.",
                "test_effectiveness": {"passed": 2, "coverage": 0.94},
            },
        )
        create(
            client,
            "event-inbox",
            {
                **common,
                "event_id": str(uuid.uuid4()),
                "topic_name": "enterprise.failures",
                "event_type": "api.timeout",
                "payload": {"payload_ref": "obs://verification/failure-payload"},
                "processing_status": "SUCCESS",
            },
        )
        create(
            client,
            "event-outbox",
            {
                **common,
                "topic_name": "art.execution-intents",
                "event_type": "execution.intent.approved",
                "payload": {"execution_intent_id": intent["resource_id"]},
                "publish_status": "RECEIVED",
            },
        )

        trace = client.get(f"/v1/art/correlations/{correlation_id}")
        trace.raise_for_status()
        print(f"correlation trace rows: {len(trace.json()['records'])}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
