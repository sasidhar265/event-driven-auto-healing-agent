import json
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event, KnowledgeItem, Policy, RemediationReference, SuggestionStatus


@dataclass(frozen=True)
class Candidate:
    agent_type: str
    title: str
    rationale: str
    proposed_changes: dict[str, Any]
    base_confidence: float


@dataclass(frozen=True)
class FailureRoute:
    """Explainable result of classifying an incoming failure."""

    category: str
    confidence: float
    matched_signals: tuple[str, ...]
    alternatives: tuple[tuple[str, float], ...]
    ambiguous: bool = False


class FailureRouter:
    """Classify failures before invoking a specialist.

    Explicit structured fields are weighted more strongly than free text. This
    prevents a stack trace mentioning an HTTP client, for example, from
    overriding an explicitly declared UI failure.
    """

    SIGNALS: dict[str, dict[str, float]] = {
        "ui": {
            "ui": 1.0, "frontend": 1.0, "browser": 1.2, "render": 0.8,
            "layout": 0.8, "xpath": 2.0, "selector": 1.2, "locator": 1.2,
            "nosuchelement": 2.0, "element_not_found": 2.0, "dom": 1.2,
            "playwright": 1.3, "selenium": 1.3,
        },
        "api": {
            "api": 1.2, "http": 1.0, "endpoint": 1.0, "gateway": 1.2,
            "request": 0.6, "response": 0.6, "timeout": 1.0,
            "status_code": 1.3, "readtimeout": 1.4, "connectionerror": 1.4,
        },
        "logic": {
            "exception": 0.8, "null": 1.1, "none": 0.5, "calculation": 1.0,
            "assertionerror": 1.2, "typeerror": 1.2, "valueerror": 1.2,
            "keyerror": 1.2, "indexerror": 1.2, "state": 0.6,
        },
        "functional": {
            "workflow": 1.3, "business": 1.1, "functional": 1.3,
            "process": 0.8, "expected_result": 1.0, "actual_result": 1.0,
            "acceptance": 0.9,
        },
        "test_data": {
            "fixture": 1.5, "test data": 1.5, "test_data": 1.5, "seed": 1.1,
            "dataset": 1.2, "mock": 1.0, "factory": 0.8,
        },
        "database": {
            "database": 1.3, "postgres": 1.4, "sql": 1.0, "query": 0.8,
            "deadlock": 2.0, "lock timeout": 1.7, "connection pool": 1.6,
            "uniqueviolation": 1.7, "foreignkeyviolation": 1.7,
            "migration": 1.2, "relation does not exist": 1.8,
        },
        "infrastructure": {
            "infrastructure": 1.4, "kubernetes": 1.5, "pod": 0.9,
            "container": 0.8, "crashloopbackoff": 2.0, "oomkilled": 2.0,
            "cpu": 1.0, "memory": 1.0, "disk": 1.0, "node": 0.7,
            "unhealthy": 1.0, "capacity": 1.2,
        },
        "dependency": {
            "dependency": 1.4, "upstream": 1.2, "downstream": 1.2,
            "service unavailable": 1.5, "connection refused": 1.5,
            "dns": 1.5, "circuit breaker": 1.5, "third party": 1.3,
            "version conflict": 1.5,
        },
        "security": {
            "security": 1.5, "unauthorized": 1.4, "forbidden": 1.3,
            "authentication": 1.3, "authorization": 1.3, "permission": 1.0,
            "certificate": 1.4, "token expired": 1.4, "vulnerability": 1.8,
            "secret": 1.0, "cve": 1.8,
        },
        "performance": {
            "performance": 1.4, "latency": 1.3, "slow": 1.0,
            "throughput": 1.2, "regression": 0.8, "p95": 1.2, "p99": 1.2,
            "memory leak": 1.8, "n+1": 1.7, "bottleneck": 1.4,
        },
    }

    def classify(self, event: Event) -> FailureRoute:
        payload = event.payload if isinstance(event.payload, dict) else {}
        explicit = str(payload.get("failure_category") or payload.get("component_type") or "").lower()
        searchable = json.dumps(
            {"event_type": event.event_type, "source": getattr(event, "source", ""), "payload": payload},
            default=str,
        ).lower()
        scores = {category: 0.0 for category in self.SIGNALS}
        matched: dict[str, list[str]] = {category: [] for category in self.SIGNALS}

        if explicit in scores:
            scores[explicit] += 6.0
            matched[explicit].append(f"explicit:{explicit}")

        structured_hints = {
            "ui": ("failed_locator", "dom_candidates", "screenshot_url"),
            "api": ("endpoint", "http_method", "status_code", "request", "response"),
            "logic": ("stack_trace", "exception_type", "source_file", "method_name"),
            "functional": ("expected_result", "actual_result", "workflow"),
            "test_data": ("fixture", "dataset", "seed_data"),
            "database": ("database_system", "sql_state", "query", "table", "migration"),
            "infrastructure": (
                "cluster", "namespace", "pod", "container", "resource_metrics"
            ),
            "dependency": (
                "dependency_name", "dependency_endpoint", "upstream_status"
            ),
            "security": (
                "security_control", "principal", "permission", "certificate_expiry"
            ),
            "performance": (
                "baseline_ms", "observed_ms", "p95_ms", "profile", "slow_query"
            ),
        }
        for category, fields in structured_hints.items():
            for field in fields:
                if payload.get(field) not in (None, "", [], {}):
                    scores[category] += 1.5
                    matched[category].append(f"field:{field}")

        for category, signals in self.SIGNALS.items():
            for signal, weight in signals.items():
                if signal in searchable:
                    scores[category] += weight
                    matched[category].append(signal)

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        category, top_score = ranked[0]
        second_score = ranked[1][1]
        if top_score == 0:
            return FailureRoute("unknown", 0.0, (), tuple(ranked[1:3]), True)

        # Signal strength and separation from the next category both matter.
        confidence = min(0.99, 0.50 + min(top_score, 6.0) * 0.06 + min(top_score - second_score, 3.0) * 0.04)
        ambiguous = top_score - second_score < 0.75 and explicit not in scores
        if ambiguous:
            confidence = min(confidence, 0.59)
        return FailureRoute(
            category, confidence, tuple(dict.fromkeys(matched[category])),
            tuple(ranked[1:3]), ambiguous,
        )


class KnowledgeService:
    async def search(self, session: AsyncSession, event: Event) -> list[dict[str, Any]]:
        words = set(re.findall(r"[a-z0-9_]+", f"{event.event_type} {event.payload}".lower()))
        items = (await session.scalars(
            select(KnowledgeItem).where(KnowledgeItem.tenant_id == event.tenant_id).limit(50)
        )).all()
        ranked: list[tuple[int, str, Any]] = []
        for item in items:
            item_words = set(re.findall(
                r"[a-z0-9_]+",
                f"{item.title} {' '.join(item.tags)} {item.content}".lower(),
            ))
            score = len(words.intersection(item_words))
            if score:
                ranked.append((score, "knowledge", item))
        references = (await session.scalars(select(RemediationReference).where(
            RemediationReference.tenant_id == event.tenant_id,
            RemediationReference.active.is_(True),
        ).order_by(RemediationReference.created_at.desc()).limit(100))).all()
        for reference in references:
            reference_words = set(re.findall(
                r"[a-z0-9_]+",
                f"{reference.event_type} {reference.agent_type} "
                f"{reference.title} {reference.rationale}".lower(),
            ))
            score = len(words.intersection(reference_words))
            if score:
                ranked.append((score + 1, "accepted_remediation", reference))
        evidence: list[dict[str, Any]] = []
        for score, kind, item in sorted(ranked, key=lambda row: row[0], reverse=True)[:5]:
            if kind == "knowledge":
                evidence.append({
                    "type": kind, "id": str(item.id), "title": item.title,
                    "content": item.content, "score": score,
                })
            else:
                item.use_count += 1
                item.last_used_at = datetime.now(UTC)
                evidence.append({
                    "type": kind, "id": str(item.id), "title": item.title,
                    "content": item.rationale, "score": score,
                    "agent_type": item.agent_type,
                    "proposed_changes": item.proposed_changes,
                    "source_suggestion_id": str(item.suggestion_id),
                    "outcome": item.outcome,
                })
        return evidence


class Agent(Protocol):
    agent_type: str

    async def suggest(self, event: Event, evidence: list[dict[str, Any]]) -> Candidate | None: ...


class AIService:
    """Optional enterprise AI gateway adapter; deterministic behavior is the safe default."""

    async def enrich(self, event: Event, candidate: Candidate, evidence: list[dict[str, Any]]) -> Candidate:
        from app.config import get_settings

        settings = get_settings()
        if settings.ai_provider == "deterministic" or not settings.ai_endpoint:
            return candidate
        headers = {"Authorization": f"Bearer {settings.ai_api_key}"} if settings.ai_api_key else {}
        request = {
            "event": {"type": event.event_type, "severity": event.severity, "payload": event.payload},
            "candidate": candidate.__dict__, "evidence": evidence,
        }
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(settings.ai_endpoint, json=request, headers=headers)
            response.raise_for_status()
            result = response.json()
        # The gateway may enrich explanation/change details, but cannot select status or bypass policy.
        return replace(
            candidate,
            rationale=str(result.get("rationale", candidate.rationale))[:5000],
            proposed_changes=result.get("proposed_changes", candidate.proposed_changes),
            base_confidence=max(0.0, min(float(result.get("confidence", candidate.base_confidence)), 1.0)),
        )


class PatternAgent:
    def __init__(self, agent_type: str, signals: set[str], action: str):
        self.agent_type, self.signals, self.action = agent_type, signals, action

    async def suggest(self, event: Event, evidence: list[dict[str, Any]]) -> Candidate | None:
        text = f"{event.event_type} {event.payload}".lower()
        matches = [signal for signal in self.signals if signal in text]
        if not matches:
            return None
        evidence_bonus = min(len(evidence) * 0.04, 0.12)
        severity_bonus = {"critical": 0.08, "error": 0.05, "warning": 0.02}.get(event.severity, 0)
        return Candidate(
            agent_type=self.agent_type,
            title=f"{self.agent_type.title()} remediation for {event.event_type}",
            rationale=f"Matched signals: {', '.join(matches)}. Correlated knowledge: {len(evidence)} item(s).",
            proposed_changes={"action": self.action, "signals": matches, "parameters": event.payload},
            base_confidence=min(0.62 + 0.06 * len(matches) + evidence_bonus + severity_bonus, 0.97),
        )


class TargetedRepairAgent(PatternAgent):
    """Create a file/method-level repair plan when the event supplies locations."""

    REQUIRED_EVIDENCE = {
        "ui": ["failed locator or screenshot/DOM", "test file and test name"],
        "api": ["endpoint and observed response/error", "trace or relevant logs"],
        "logic": ["exception type and stack trace", "source file or failing method"],
        "functional": ["expected result and actual result", "workflow step"],
        "test_data": ["fixture/dataset identifier", "expected schema or values"],
        "database": ["database error/SQL state", "query or migration identifier"],
        "infrastructure": ["resource identity", "current metrics and desired state"],
        "dependency": ["dependency identity and endpoint", "upstream response or health"],
        "security": ["failed security control and principal", "sanitized authentication evidence"],
        "performance": ["baseline and observed measurement", "trace/profile or slow query"],
    }

    async def suggest(self, event: Event, evidence: list[dict[str, Any]]) -> Candidate | None:
        candidate = await super().suggest(event, evidence)
        if not candidate:
            return None
        payload = event.payload
        target_file = (
            payload.get("source_file") or payload.get("test_file")
            or payload.get("manifest_file") or payload.get("config_file")
            or payload.get("migration_file") or payload.get("policy_file")
        )
        target_method = (
            payload.get("method_name") or payload.get("test_name")
            or payload.get("resource_name") or payload.get("query_name")
        )
        exception_type = payload.get("exception_type")
        stack_trace = payload.get("stack_trace")
        expected = payload.get("expected_result")
        actual = payload.get("actual_result")
        missing = []
        if not target_file:
            missing.append("source_file or test_file")
        if self.agent_type in {"logic", "api"} and not (stack_trace or payload.get("trace_id")):
            missing.append("stack_trace or trace_id")

        proposed = {
            **candidate.proposed_changes,
            "target": {"file": target_file, "method": target_method},
            "diagnosis": {
                "exception_type": exception_type,
                "error": payload.get("error") or payload.get("message"),
                "expected": expected,
                "actual": actual,
            },
            "change_plan": self._change_plan(),
            "validation": self._validation(payload),
            "rollback": "revert the proposed file-level change and rerun the failing test",
        }
        confidence = candidate.base_confidence
        if target_file:
            confidence += 0.04
        if target_method:
            confidence += 0.03
        if stack_trace or payload.get("trace_id"):
            confidence += 0.03
        if missing:
            proposed["required_evidence"] = missing + self.REQUIRED_EVIDENCE[self.agent_type]
            confidence = min(confidence, 0.59)
        return replace(candidate, proposed_changes=proposed, base_confidence=min(confidence, 0.97))

    def _change_plan(self) -> list[dict[str, str]]:
        plans = {
            "ui": [
                {"step": "inspect", "instruction": "Compare the failed UI assertion/locator with the supplied DOM and screenshot."},
                {"step": "change", "instruction": "Update the smallest affected component or test locator; prefer stable test IDs."},
            ],
            "api": [
                {"step": "inspect", "instruction": "Trace the failing endpoint through its handler and downstream call using the trace ID."},
                {"step": "change", "instruction": "Correct the failing handler/dependency boundary; do not merely increase a timeout without latency evidence."},
            ],
            "logic": [
                {"step": "inspect", "instruction": "Use the first application frame in the stack trace to locate the failing branch."},
                {"step": "change", "instruction": "Correct the violated invariant at its source and add a regression test for the observed input."},
            ],
            "functional": [
                {"step": "inspect", "instruction": "Compare expected and actual workflow state at the failing step."},
                {"step": "change", "instruction": "Correct the transition or business rule and preserve adjacent valid transitions."},
            ],
            "test_data": [
                {"step": "inspect", "instruction": "Compare the fixture/dataset with the current input schema and test expectation."},
                {"step": "change", "instruction": "Update the smallest invalid fixture value or factory default."},
            ],
            "database": [
                {"step": "inspect", "instruction": "Use SQL state, query identity, locks, and the execution plan to establish the database cause."},
                {"step": "change", "instruction": "Apply the smallest query, index, constraint, pool, or migration correction; preserve transactional integrity."},
            ],
            "infrastructure": [
                {"step": "inspect", "instruction": "Compare workload events and resource metrics with the declared deployment state."},
                {"step": "change", "instruction": "Correct the owning manifest or capacity setting with explicit blast-radius and rollback limits."},
            ],
            "dependency": [
                {"step": "inspect", "instruction": "Confirm dependency health, contract, DNS, TLS, and retry/circuit-breaker behavior."},
                {"step": "change", "instruction": "Correct the dependency boundary or resilience policy without hiding a persistent upstream failure."},
            ],
            "security": [
                {"step": "inspect", "instruction": "Validate identity, authorization policy, credential age, and certificate evidence without exposing secrets."},
                {"step": "change", "instruction": "Restore least-privilege access or rotate the affected credential through the approved security workflow."},
            ],
            "performance": [
                {"step": "inspect", "instruction": "Compare the trace/profile with a known baseline and locate the dominant latency or allocation contributor."},
                {"step": "change", "instruction": "Optimize the measured bottleneck and preserve response correctness under representative load."},
            ],
        }
        return plans[self.agent_type]

    def _validation(self, payload: dict[str, Any]) -> list[str]:
        test_name = payload.get("test_name")
        checks = [
            f"rerun the originally failing test{f' {test_name}' if test_name else ''}",
            "run the owning component regression suite",
            "confirm the original error and observable symptom are absent",
        ]
        if self.agent_type == "api":
            checks.append("verify response contract, latency, and downstream error rate")
        elif self.agent_type == "database":
            checks.extend(["verify transaction correctness and query plan", "monitor lock and pool metrics"])
        elif self.agent_type == "infrastructure":
            checks.extend(["apply first in a non-production environment", "verify health, saturation, and rollback"])
        elif self.agent_type == "dependency":
            checks.append("exercise timeout, retry, and circuit-breaker behavior")
        elif self.agent_type == "security":
            checks.extend(["run authorization regression tests", "confirm no credential is logged or embedded"])
        elif self.agent_type == "performance":
            checks.append("repeat the benchmark and compare p50/p95/p99 with baseline")
        return checks


class XPathInvestigationAgent:
    agent_type = "ui"

    async def suggest(self, event: Event, evidence: list[dict[str, Any]]) -> Candidate | None:
        text = f"{event.event_type} {event.payload}".lower()
        if not any(signal in text for signal in ("xpath", "nosuchelement", "element_not_found")):
            return None
        locator = event.payload.get("failed_locator", {})
        candidates = event.payload.get("dom_candidates", [])
        if not isinstance(candidates, list) or not candidates:
            return Candidate(
                agent_type=self.agent_type,
                title="Collect current DOM evidence for failed XPath",
                rationale="The XPath failed, but no current DOM candidates were supplied; a safe replacement cannot be inferred.",
                proposed_changes={
                    "action": "collect_dom_snapshot", "failed_locator": locator,
                    "required_evidence": ["sanitized DOM near target", "screenshot", "successful locator history"],
                },
                base_confidence=0.58,
            )
        ranked: list[tuple[int, dict[str, Any], str, str]] = []
        for node in candidates:
            attrs = node.get("attributes", {}) if isinstance(node, dict) else {}
            strategies = [
                (100, "css-selector", f'[data-testid="{attrs["data-testid"]}"]') if attrs.get("data-testid") else None,
                (85, "id", attrs.get("id")) if attrs.get("id") else None,
                (70, "css-selector", f'[name="{attrs["name"]}"]') if attrs.get("name") else None,
                (60, "css-selector", f'[aria-label="{attrs["aria-label"]}"]') if attrs.get("aria-label") else None,
            ]
            for strategy in strategies:
                if strategy:
                    score, kind, value = strategy
                    ranked.append((score, node, kind, value))
        if not ranked:
            return None
        score, node, strategy, value = max(ranked, key=lambda item: item[0])
        unique = sum(
            1 for candidate in candidates
            if candidate.get("attributes", {}).get("data-testid") == node.get("attributes", {}).get("data-testid")
        ) == 1 if node.get("attributes", {}).get("data-testid") else False
        confidence = 0.72 + (0.12 if score == 100 else 0.05) + (0.06 if unique else 0) + min(len(evidence) * 0.03, 0.09)
        return Candidate(
            agent_type=self.agent_type,
            title="Replace obsolete XPath with a stable locator",
            rationale=f"The failed XPath no longer resolves. A current DOM candidate provides a {strategy} locator"
            f"{' that is unique in supplied evidence' if unique else ''}.",
            proposed_changes={
                "action": "replace_test_locator", "target_file": event.payload.get("test_file"),
                "test_name": event.payload.get("test_name"), "current_locator": locator,
                "recommended_locator": {"strategy": strategy, "value": value},
                "matched_element": node,
                "validation": ["assert locator resolves exactly one element", "run failed test", "run owning UI regression suite"],
                "rollback": "restore the previous test locator",
            },
            base_confidence=min(confidence, 0.97),
        )


def specialist_agents() -> list[Agent]:
    return [
        XPathInvestigationAgent(),
        TargetedRepairAgent("ui", {"ui", "frontend", "render", "browser", "layout"}, "propose_ui_patch"),
        TargetedRepairAgent("api", {"api", "http", "timeout", "endpoint", "gateway"}, "propose_api_change"),
        TargetedRepairAgent("logic", {"exception", "null", "logic", "calculation", "state"}, "propose_logic_patch"),
        TargetedRepairAgent("functional", {"workflow", "business", "functional", "process"}, "propose_workflow_change"),
        TargetedRepairAgent("test_data", {"fixture", "test data", "seed", "dataset", "mock"}, "propose_test_data_change"),
        TargetedRepairAgent(
            "database",
            {"database", "postgres", "sql", "query", "deadlock", "migration"},
            "propose_database_change",
        ),
        TargetedRepairAgent(
            "infrastructure",
            {"infrastructure", "kubernetes", "pod", "container", "oomkilled", "cpu", "memory", "capacity"},
            "propose_infrastructure_change",
        ),
        TargetedRepairAgent(
            "dependency",
            {"dependency", "upstream", "downstream", "service unavailable", "dns", "circuit breaker"},
            "propose_dependency_change",
        ),
        TargetedRepairAgent(
            "security",
            {"security", "unauthorized", "forbidden", "authentication", "permission", "certificate", "cve"},
            "propose_security_change",
        ),
        TargetedRepairAgent(
            "performance",
            {"performance", "latency", "slow", "throughput", "p95", "p99", "memory leak", "bottleneck"},
            "propose_performance_change",
        ),
    ]


class EvidenceRequestAgent:
    agent_type = "investigation"

    def __init__(self, route: FailureRoute):
        self.route = route

    async def suggest(self, event: Event, evidence: list[dict[str, Any]]) -> Candidate:
        return Candidate(
            agent_type=self.agent_type,
            title=f"Collect evidence to classify {event.event_type}",
            rationale="The failure category is unknown or ambiguous, so proposing a code change would be unsafe.",
            proposed_changes={
                "action": "collect_failure_evidence",
                "routing": route_details(self.route),
                "required_evidence": [
                    "exception type and complete application stack trace",
                    "source/test file and failing method/test name",
                    "expected and actual result",
                    "relevant logs and distributed trace ID",
                    "UI DOM/screenshot or API request/response details when applicable",
                ],
            },
            base_confidence=0.40,
        )


def route_details(route: FailureRoute) -> dict[str, Any]:
    return {
        "category": route.category,
        "confidence": route.confidence,
        "matched_signals": list(route.matched_signals),
        "alternatives": [{"category": name, "score": score} for name, score in route.alternatives],
        "ambiguous": route.ambiguous,
    }


def routed_agents(event: Event) -> tuple[FailureRoute, list[Agent]]:
    """Return only specialists appropriate for this failure."""

    route = FailureRouter().classify(event)
    if route.category == "unknown" or route.ambiguous:
        return route, [EvidenceRequestAgent(route)]
    agents = specialist_agents()
    if route.category == "ui":
        text = f"{event.event_type} {event.payload}".lower()
        if any(signal in text for signal in ("xpath", "nosuchelement", "element_not_found")):
            return route, [agents[0]]
    return route, [agent for agent in agents if agent.agent_type == route.category][0:1]


class PolicyEngine:
    async def evaluate(
        self, session: AsyncSession, event: Event, candidate: Candidate
    ) -> tuple[SuggestionStatus, dict[str, Any], float]:
        policies = (await session.scalars(select(Policy).where(
            Policy.tenant_id == event.tenant_id, Policy.active.is_(True)
        ))).all()
        confidence = candidate.base_confidence
        violations: list[str] = []
        approvals: list[str] = []
        for policy in policies:
            rules = policy.rules
            if candidate.agent_type in rules.get("blocked_agent_types", []):
                violations.append(f"{policy.name}: agent type blocked")
            if event.severity in rules.get("human_review_severities", []):
                approvals.append(f"{policy.name}: human review required")
            confidence += float(rules.get("confidence_adjustments", {}).get(candidate.agent_type, 0))
        confidence = max(0.0, min(confidence, 1.0))
        from app.config import get_settings

        settings = get_settings()
        if violations:
            status = SuggestionStatus.SUPPRESSED
        elif approvals or confidence < settings.confidence_delivery_threshold:
            status = SuggestionStatus.REVIEW if confidence >= settings.confidence_review_threshold else SuggestionStatus.SUPPRESSED
        else:
            status = SuggestionStatus.READY
        return status, {"violations": violations, "approvals": approvals, "policies": len(policies)}, confidence
