"""CloudEvents payload construction for suggestion delivery."""

from app.models import Suggestion
from app.runtime_config import get_runtime_rules


def cloud_event(suggestion: Suggestion) -> dict:
    """Serialize a ready suggestion as the downstream CloudEvents payload."""
    delivery = get_runtime_rules().delivery
    return {
        "specversion": "1.0", "id": str(suggestion.id),
        "source": delivery.cloud_event_source, "type": delivery.cloud_event_type,
        "subject": str(suggestion.event_id), "time": suggestion.created_at.isoformat(),
        "datacontenttype": "application/json", "tenantid": suggestion.tenant_id,
        "data": {
            "suggestion_id": str(suggestion.id), "event_id": str(suggestion.event_id),
            "agent_type": suggestion.agent_type, "title": suggestion.title,
            "rationale": suggestion.rationale,
            "proposed_changes": suggestion.proposed_changes,
            "evidence": suggestion.evidence, "confidence": suggestion.confidence,
            "policy_result": suggestion.policy_result, "status": suggestion.status.value,
        },
    }
