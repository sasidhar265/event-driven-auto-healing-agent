"""Optional enterprise AI enrichment behind deterministic governance."""

from dataclasses import replace
from typing import Any

import httpx

from app.models import Event
from app.services.types import Candidate

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
