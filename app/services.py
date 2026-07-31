import json
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event, KnowledgeItem, Policy, RemediationReference, SuggestionStatus
from app.runtime_config import get_runtime_rules


@dataclass(frozen=True)
class Candidate:
    """A specialist agent's proposed remediation before governance is applied."""
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

    def classify(self, event: Event) -> FailureRoute:
        """Score event fields and signals to select an explainable failure route."""
        config = get_runtime_rules().routing
        scoring = config.scoring
        payload = event.payload if isinstance(event.payload, dict) else {}
        explicit = next(
            (
                str(payload[field]).lower()
                for field in config.explicit_fields
                if payload.get(field)
            ),
            "",
        )
        searchable = json.dumps(
            {"event_type": event.event_type, "source": getattr(event, "source", ""), "payload": payload},
            default=str,
        ).lower()
        scores = {category: 0.0 for category in config.signals}
        matched: dict[str, list[str]] = {category: [] for category in config.signals}

        if explicit in scores:
            scores[explicit] += scoring.explicit_weight
            matched[explicit].append(f"explicit:{explicit}")

        for category, fields in config.structured_hints.items():
            for field in fields:
                if payload.get(field) not in (None, "", [], {}):
                    scores[category] += scoring.structured_field_weight
                    matched[category].append(f"field:{field}")

        for category, signals in config.signals.items():
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
        confidence = min(
            scoring.confidence_cap,
            scoring.confidence_base
            + min(top_score, scoring.score_cap) * scoring.score_multiplier
            + min(top_score - second_score, scoring.separation_cap)
            * scoring.separation_multiplier,
        )
        ambiguous = (
            top_score - second_score < scoring.ambiguity_margin
            and explicit not in scores
        )
        if ambiguous:
            confidence = min(confidence, scoring.ambiguous_confidence_cap)
        return FailureRoute(
            category, confidence, tuple(dict.fromkeys(matched[category])),
            tuple(ranked[1:3]), ambiguous,
        )


class KnowledgeService:
    """Retrieves tenant knowledge and accepted remediations as agent evidence."""
    async def search(self, session: AsyncSession, event: Event) -> list[dict[str, Any]]:
        """Return relevant knowledge and prior accepted fixes for an event."""
        config = get_runtime_rules().knowledge
        words = set(re.findall(r"[a-z0-9_]+", f"{event.event_type} {event.payload}".lower()))
        items = (await session.scalars(
            select(KnowledgeItem).where(KnowledgeItem.tenant_id == event.tenant_id)
            .limit(config.item_scan_limit)
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
        ).order_by(RemediationReference.created_at.desc())
        .limit(config.reference_scan_limit))).all()
        for reference in references:
            reference_words = set(re.findall(
                r"[a-z0-9_]+",
                f"{reference.event_type} {reference.agent_type} "
                f"{reference.title} {reference.rationale}".lower(),
            ))
            score = len(words.intersection(reference_words))
            if score:
                ranked.append(
                    (score + config.accepted_reference_bonus, "accepted_remediation", reference)
                )
        evidence: list[dict[str, Any]] = []
        for score, kind, item in sorted(
            ranked, key=lambda row: row[0], reverse=True
        )[:config.result_limit]:
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
    """Interface implemented by every remediation specialist."""
    agent_type: str

    async def suggest(
        self, event: Event, evidence: list[dict[str, Any]]
    ) -> Candidate | None:
        """Return a remediation candidate or abstain when the event is irrelevant."""
        ...


class AIService:
    """Optional enterprise AI gateway adapter; deterministic behavior is the safe default."""

    async def enrich(self, event: Event, candidate: Candidate, evidence: list[dict[str, Any]]) -> Candidate:
        """Optionally enrich a candidate through the configured enterprise AI gateway."""
        from app.config import get_settings

        settings = get_settings()
        if settings.ai_provider == "deterministic" or not settings.ai_endpoint:
            return candidate
        headers = {"Authorization": f"Bearer {settings.ai_api_key}"} if settings.ai_api_key else {}
        request = {
            "event": {"type": event.event_type, "severity": event.severity, "payload": event.payload},
            "candidate": candidate.__dict__, "evidence": evidence,
        }
        async with httpx.AsyncClient(timeout=settings.ai_timeout_seconds) as client:
            response = await client.post(settings.ai_endpoint, json=request, headers=headers)
            response.raise_for_status()
            result = response.json()
        # The gateway may enrich explanation/change details, but cannot select status or bypass policy.
        return replace(
            candidate,
            rationale=str(result.get("rationale", candidate.rationale))[
                :settings.ai_rationale_max_length
            ],
            proposed_changes=result.get("proposed_changes", candidate.proposed_changes),
            base_confidence=max(0.0, min(float(result.get("confidence", candidate.base_confidence)), 1.0)),
        )


class PatternAgent:
    """Configured specialist that emits a candidate when its signals match."""
    def __init__(self, agent_type: str, signals: set[str], action: str):
        """Bind a specialist name, matching signals, and proposed action."""
        self.agent_type, self.signals, self.action = agent_type, signals, action

    async def suggest(self, event: Event, evidence: list[dict[str, Any]]) -> Candidate | None:
        """Return a configured candidate when the event matches this specialist."""
        agent_config = get_runtime_rules().agents
        tuning = agent_config.confidence
        text = f"{event.event_type} {event.payload}".lower()
        matches = [signal for signal in self.signals if signal in text]
        if not matches:
            return None
        evidence_bonus = min(
            len(evidence) * tuning.evidence_bonus_per_item,
            tuning.evidence_bonus_cap,
        )
        severity_bonus = tuning.severity_bonus.get(event.severity, 0)
        return Candidate(
            agent_type=self.agent_type,
            title=agent_config.title_template.format(
                agent_type=self.agent_type.title(),
                event_type=event.event_type,
            ),
            rationale=agent_config.rationale_template.format(
                matches=", ".join(matches),
                evidence_count=len(evidence),
            ),
            proposed_changes={"action": self.action, "signals": matches, "parameters": event.payload},
            base_confidence=min(
                tuning.base
                + tuning.signal_bonus * len(matches)
                + evidence_bonus
                + severity_bonus,
                tuning.maximum,
            ),
        )


class TargetedRepairAgent(PatternAgent):
    """Create a file/method-level repair plan when the event supplies locations."""

    async def suggest(self, event: Event, evidence: list[dict[str, Any]]) -> Candidate | None:
        """Build a targeted repair candidate with change and validation plans."""
        agent_config = get_runtime_rules().agents
        tuning = agent_config.confidence
        candidate = await super().suggest(event, evidence)
        if not candidate:
            return None
        payload = event.payload
        target_file = next(
            (payload[field] for field in agent_config.target_file_fields if payload.get(field)),
            None,
        )
        target_method = next(
            (
                payload[field]
                for field in agent_config.target_method_fields
                if payload.get(field)
            ),
            None,
        )
        exception_type = payload.get("exception_type")
        stack_trace = payload.get("stack_trace")
        expected = payload.get("expected_result")
        actual = payload.get("actual_result")
        missing = []
        if not target_file:
            missing.append(agent_config.missing_target_evidence)
        if self.agent_type in agent_config.trace_required_categories and not (
            stack_trace or payload.get("trace_id")
        ):
            missing.append(agent_config.missing_trace_evidence)

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
            "rollback": agent_config.rollback_instruction,
        }
        confidence = candidate.base_confidence
        if target_file:
            confidence += tuning.target_file_bonus
        if target_method:
            confidence += tuning.target_method_bonus
        if stack_trace or payload.get("trace_id"):
            confidence += tuning.trace_bonus
        if missing:
            required = agent_config.specialists[self.agent_type].required_evidence
            proposed["required_evidence"] = missing + required
            confidence = min(confidence, tuning.missing_evidence_cap)
        return replace(
            candidate,
            proposed_changes=proposed,
            base_confidence=min(confidence, tuning.maximum),
        )

    def _change_plan(self) -> list[dict[str, str]]:
        """Return the configured ordered repair steps for this specialist."""
        return get_runtime_rules().agents.specialists[self.agent_type].change_plan

    def _validation(self, payload: dict[str, Any]) -> list[str]:
        """Build verification instructions using available event context."""
        test_name = payload.get("test_name")
        config = get_runtime_rules().agents
        checks = list(config.base_validation)
        if test_name:
            checks[0] = f"{checks[0]} {test_name}"
        checks.extend(config.specialists[self.agent_type].validation)
        return checks


class XPathInvestigationAgent:
    """Specialist for unstable, missing, or ambiguous UI element locators."""
    agent_type = "ui"

    async def suggest(self, event: Event, evidence: list[dict[str, Any]]) -> Candidate | None:
        """Recommend a stable locator or request additional DOM evidence."""
        config = get_runtime_rules().agents.xpath
        text = f"{event.event_type} {event.payload}".lower()
        if not any(signal in text for signal in config.detection_signals):
            return None
        locator = event.payload.get("failed_locator", {})
        candidates = event.payload.get("dom_candidates", [])
        if not isinstance(candidates, list) or not candidates:
            return Candidate(
                agent_type=self.agent_type,
                title=config.missing_title,
                rationale=config.missing_rationale,
                proposed_changes={
                    "action": config.missing_action, "failed_locator": locator,
                    "required_evidence": config.required_evidence,
                },
                base_confidence=config.missing_evidence_confidence,
            )
        ranked: list[tuple[int, dict[str, Any], str, str]] = []
        for node in candidates:
            attrs = node.get("attributes", {}) if isinstance(node, dict) else {}
            strategies = [
                (config.locator_priorities["data-testid"], "css-selector", f'[data-testid="{attrs["data-testid"]}"]') if attrs.get("data-testid") else None,
                (config.locator_priorities["id"], "id", attrs.get("id")) if attrs.get("id") else None,
                (config.locator_priorities["name"], "css-selector", f'[name="{attrs["name"]}"]') if attrs.get("name") else None,
                (config.locator_priorities["aria-label"], "css-selector", f'[aria-label="{attrs["aria-label"]}"]') if attrs.get("aria-label") else None,
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
        preferred_score = config.locator_priorities["data-testid"]
        confidence = (
            config.confidence_base
            + (
                config.preferred_locator_bonus
                if score == preferred_score
                else config.other_locator_bonus
            )
            + (config.unique_bonus if unique else 0)
            + min(
                len(evidence) * config.evidence_bonus_per_item,
                config.evidence_bonus_cap,
            )
        )
        return Candidate(
            agent_type=self.agent_type,
            title=config.replacement_title,
            rationale=config.replacement_rationale.format(
                strategy=strategy,
                unique_suffix=(
                    " that is unique in supplied evidence" if unique else ""
                ),
            ),
            proposed_changes={
                "action": config.replacement_action,
                "target_file": event.payload.get("test_file"),
                "test_name": event.payload.get("test_name"), "current_locator": locator,
                "recommended_locator": {"strategy": strategy, "value": value},
                "matched_element": node,
                "validation": config.validation,
                "rollback": config.rollback_instruction,
            },
            base_confidence=min(confidence, config.maximum),
        )


def specialist_agents() -> list[Agent]:
    """Construct the specialist agents declared in runtime configuration."""
    specialists = get_runtime_rules().agents.specialists
    return [
        XPathInvestigationAgent(),
        *[
            TargetedRepairAgent(category, set(config.signals), config.action)
            for category, config in specialists.items()
        ],
    ]


class EvidenceRequestAgent:
    """Fallback agent that requests missing evidence instead of guessing a fix."""
    agent_type = "investigation"

    def __init__(self, route: FailureRoute):
        """Keep the ambiguous route details for the evidence request."""
        self.route = route

    async def suggest(self, event: Event, evidence: list[dict[str, Any]]) -> Candidate:
        """Create a review-only candidate describing the missing evidence."""
        config = get_runtime_rules().agents.investigation
        return Candidate(
            agent_type=self.agent_type,
            title=config.title_template.format(event_type=event.event_type),
            rationale=config.rationale,
            proposed_changes={
                "action": config.action,
                "routing": route_details(self.route),
                "required_evidence": config.required_evidence,
            },
            base_confidence=config.confidence,
        )


def route_details(route: FailureRoute) -> dict[str, Any]:
    """Convert a route into JSON-safe details for audit and suggestion output."""
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
        if any(
            signal in text
            for signal in get_runtime_rules().agents.xpath.detection_signals
        ):
            return route, [agents[0]]
    return route, [agent for agent in agents if agent.agent_type == route.category][0:1]


class PolicyEngine:
    """Applies tenant governance and confidence gates to agent candidates."""
    async def evaluate(
        self, session: AsyncSession, event: Event, candidate: Candidate
    ) -> tuple[SuggestionStatus, dict[str, Any], float]:
        """Return governed status, policy explanation, and final confidence."""
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
