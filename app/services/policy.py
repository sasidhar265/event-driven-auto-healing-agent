"""Tenant policy evaluation and confidence gating."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event, SuggestionStatus
from app.repositories.governance.queries import list_active_policies
from app.services.types import Candidate

class PolicyEngine:
    """Applies tenant governance and confidence gates to agent candidates."""
    async def evaluate(
        self, session: AsyncSession, event: Event, candidate: Candidate
    ) -> tuple[SuggestionStatus, dict[str, Any], float]:
        """Return governed status, policy explanation, and final confidence."""
        policies = await list_active_policies(session, event.tenant_id)
        base_confidence = candidate.base_confidence
        confidence = base_confidence
        violations: list[str] = []
        approvals: list[str] = []
        adjustments: list[dict[str, Any]] = []
        for policy in policies:
            rules = policy.rules
            if candidate.agent_type in rules.get("blocked_agent_types", []):
                violations.append(f"{policy.name}: agent type blocked")
            if event.severity in rules.get("human_review_severities", []):
                approvals.append(f"{policy.name}: human review required")
            adjustment = float(
                rules.get("confidence_adjustments", {}).get(candidate.agent_type, 0)
            )
            confidence += adjustment
            if adjustment:
                adjustments.append({"policy": policy.name, "value": adjustment})
        before_clamp = confidence
        confidence = max(0.0, min(confidence, 1.0))
        from app.config import get_settings

        settings = get_settings()
        if violations:
            status = SuggestionStatus.SUPPRESSED
        elif approvals or confidence < settings.confidence_delivery_threshold:
            status = SuggestionStatus.REVIEW if confidence >= settings.confidence_review_threshold else SuggestionStatus.SUPPRESSED
        else:
            status = SuggestionStatus.READY
        return status, {
            "violations": violations,
            "approvals": approvals,
            "policies": len(policies),
            "confidence_calculation": {
                "specialist_base": base_confidence,
                "policy_adjustments": adjustments,
                "adjustment_total": sum(item["value"] for item in adjustments),
                "before_clamp": before_clamp,
                "minimum": 0.0,
                "maximum": 1.0,
                "final_confidence": confidence,
                "review_threshold": settings.confidence_review_threshold,
                "ready_threshold": settings.confidence_delivery_threshold,
                "decision": status.value,
                "formula": "clamp(specialist base + policy adjustments, 0, 1)",
            },
        }, confidence
