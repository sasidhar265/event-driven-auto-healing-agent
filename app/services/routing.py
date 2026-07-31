"""Failure classification and specialist selection."""

from __future__ import annotations

import json
from typing import Any

from app.models import Event
from app.runtime_config import get_runtime_rules
from app.services.types import FailureRoute

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

    from app.services.agents import Agent, EvidenceRequestAgent, specialist_agents

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
