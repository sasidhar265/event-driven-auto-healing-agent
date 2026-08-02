"""Sector-neutral incident intelligence and safe remediation planning."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

SENSITIVE_KEYS = re.compile(
    r"password|passwd|secret|token|authorization|api[_-]?key|cookie|ssn|card|patient",
    re.IGNORECASE,
)


def _first(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if SENSITIVE_KEYS.search(key) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _number(value: Any, conversion: type[int | float]) -> int | float:
    try:
        return conversion(value or 0)
    except (TypeError, ValueError):
        return conversion(0)


def normalize_incident(
    *, event_type: str, source: str, severity: str, payload: dict[str, Any]
) -> dict[str, Any]:
    """Map common vendor fields into a stable OpenTelemetry-aligned context."""
    exception = payload.get("exception") if isinstance(payload.get("exception"), dict) else {}
    resource = payload.get("resource") if isinstance(payload.get("resource"), dict) else {}
    normalized = {
        "schema_version": "1.0",
        "event_type": event_type or "unclassified.failure",
        "source": source,
        "severity": severity,
        "service": _first(payload, "service.name", "service_name", "service", "application"),
        "component": _first(payload, "component", "component_name", "resource_name"),
        "environment": _first(payload, "deployment.environment.name", "environment", "env"),
        "region": _first(payload, "cloud.region", "region"),
        "trace_id": _first(payload, "trace_id", "traceId"),
        "span_id": _first(payload, "span_id", "spanId"),
        "deployment_id": _first(payload, "deployment_id", "release_id", "version"),
        "exception": {
            "type": _first(payload, "exception.type", "exception_type", "error_type")
            or exception.get("type"),
            "message": _first(payload, "exception.message", "error", "message")
            or exception.get("message"),
            "stacktrace": _first(payload, "exception.stacktrace", "stack_trace", "stacktrace")
            or exception.get("stacktrace"),
        },
        "resource": {
            "type": _first(payload, "resource_type", "cloud.platform") or resource.get("type"),
            "id": _first(payload, "resource_id", "host.id", "container.id", "k8s.pod.uid")
            or resource.get("id"),
        },
        "business": {
            "capability": _first(payload, "business_capability", "business_service"),
            "criticality": str(
                _first(payload, "business_criticality", "criticality") or "medium"
            ).lower(),
            "affected_users": _number(_first(payload, "affected_users", "users_affected"), int),
            "revenue_exposure": _number(
                _first(payload, "revenue_exposure", "estimated_loss"), float
            ),
            "data_classification": _first(payload, "data_classification", "data_sensitivity"),
        },
    }
    return _redact(normalized)


def incident_fingerprint(context: dict[str, Any]) -> str:
    """Create a stable correlation fingerprint without volatile message text."""
    identity = {
        "event_type": context.get("event_type"),
        "service": context.get("service"),
        "component": context.get("component"),
        "exception_type": context.get("exception", {}).get("type"),
        "resource_type": context.get("resource", {}).get("type"),
        "resource_id": context.get("resource", {}).get("id"),
    }
    raw = json.dumps(identity, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def score_business_impact(context: dict[str, Any]) -> dict[str, Any]:
    """Return an explainable 0-100 priority score from cross-sector signals."""
    business = context.get("business", {})
    weights: list[dict[str, Any]] = []
    severity_points = {"info": 5, "warning": 15, "error": 30, "critical": 45}.get(
        str(context.get("severity", "error")).lower(), 20
    )
    weights.append({"signal": "technical_severity", "points": severity_points})
    criticality_points = {"low": 0, "medium": 10, "high": 20, "critical": 30}.get(
        str(business.get("criticality", "medium")).lower(), 10
    )
    weights.append({"signal": "business_criticality", "points": criticality_points})
    users = int(business.get("affected_users") or 0)
    user_points = 20 if users >= 1000 else 12 if users >= 100 else 5 if users > 0 else 0
    weights.append({"signal": "affected_users", "points": user_points})
    revenue = float(business.get("revenue_exposure") or 0)
    revenue_points = (
        15 if revenue >= 100000 else 10 if revenue >= 10000 else 5 if revenue > 0 else 0
    )
    weights.append({"signal": "revenue_exposure", "points": revenue_points})
    score = min(100, sum(item["points"] for item in weights))
    priority = "P1" if score >= 80 else "P2" if score >= 60 else "P3" if score >= 35 else "P4"
    return {"score": score, "priority": priority, "factors": weights}


@dataclass(frozen=True)
class Playbook:
    id: str
    risk: str
    signals: tuple[str, ...]
    action: str
    validation: tuple[str, ...]
    rollback: str


PLAYBOOKS = (
    Playbook(
        "restart-stateless-instance",
        "low",
        ("oomkilled", "unhealthy", "crashloop"),
        "restart one unhealthy stateless instance",
        ("replacement instance is ready", "error rate returns below threshold"),
        "restore the previous replica set",
    ),
    Playbook(
        "replay-idempotent-message",
        "low",
        ("dead-letter", "consumer lag", "kafka consumer", "failed message"),
        "replay the failed message after idempotency validation",
        ("message is acknowledged", "no duplicate business record is created"),
        "stop replay and quarantine the message",
    ),
    Playbook(
        "rollback-recent-deployment",
        "medium",
        ("deployment", "release", "regression"),
        "roll back the most recent deployment",
        ("previous version is healthy", "error rate and latency recover"),
        "redeploy the captured current version",
    ),
    Playbook(
        "dependency-failover",
        "medium",
        ("upstream", "dependency", "unavailable"),
        "route traffic to an approved healthy dependency",
        ("dependency probes pass", "business transaction succeeds"),
        "restore the original route",
    ),
)


def plan_playbook(searchable: str, context: dict[str, Any]) -> dict[str, Any] | None:
    """Select an allow-listed plan and return a non-executing safety dry run."""
    text = searchable.lower()
    playbook = next((item for item in PLAYBOOKS if any(s in text for s in item.signals)), None)
    if not playbook:
        return None
    missing = []
    if not context.get("service") and not context.get("resource", {}).get("id"):
        missing.append("service or resource identity")
    if not playbook.rollback:
        missing.append("rollback procedure")
    return {
        "id": playbook.id,
        "version": 1,
        "risk": playbook.risk,
        "mode": "dry-run",
        "action": playbook.action,
        "preconditions": {"passed": not missing, "missing": missing},
        "validation": list(playbook.validation),
        "rollback": playbook.rollback,
        "execution_authorized": False,
    }


def evaluate_recovery(before: dict[str, float], after: dict[str, float]) -> dict[str, Any]:
    """Evaluate measurable post-action health without claiming causal certainty."""
    checks = []
    for metric in ("error_rate", "latency_ms", "unhealthy_instances"):
        if metric in before and metric in after:
            checks.append(
                {
                    "metric": metric,
                    "before": before[metric],
                    "after": after[metric],
                    "improved": after[metric] < before[metric],
                }
            )
    if not checks:
        return {"status": "insufficient_evidence", "recovered": False, "checks": []}
    improved = sum(1 for check in checks if check["improved"])
    status = (
        "recovered"
        if improved == len(checks)
        else "partially_recovered"
        if improved
        else "no_effect"
    )
    return {"status": status, "recovered": status == "recovered", "checks": checks}
