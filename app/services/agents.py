"""Specialist remediation-agent implementations and construction."""

from dataclasses import replace
from typing import Any, Protocol

from app.models import Event
from app.runtime_config import get_runtime_rules
from app.services.routing import route_details
from app.services.types import Candidate, FailureRoute

class Agent(Protocol):
    """Interface implemented by every remediation specialist."""
    agent_type: str

    async def suggest(
        self, event: Event, evidence: list[dict[str, Any]]
    ) -> Candidate | None:
        """Return a remediation candidate or abstain when the event is irrelevant."""
        ...

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
