"""Tenant knowledge and accepted-remediation retrieval."""

import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event
from app.repositories.knowledge import queries as knowledge_queries
from app.runtime_config import get_runtime_rules

class KnowledgeService:
    """Retrieves tenant knowledge and accepted remediations as agent evidence."""
    async def search(self, session: AsyncSession, event: Event) -> list[dict[str, Any]]:
        """Return relevant knowledge and prior accepted fixes for an event."""
        config = get_runtime_rules().knowledge
        words = set(re.findall(r"[a-z0-9_]+", f"{event.event_type} {event.payload}".lower()))
        items = await knowledge_queries.scan_knowledge(
            session, event.tenant_id, config.item_scan_limit
        )
        ranked: list[tuple[int, str, Any]] = []
        for item in items:
            item_words = set(re.findall(
                r"[a-z0-9_]+",
                f"{item.title} {' '.join(item.tags)} {item.content}".lower(),
            ))
            score = len(words.intersection(item_words))
            if score:
                ranked.append((score, "knowledge", item))
        references = await knowledge_queries.scan_active_references(
            session, event.tenant_id, config.reference_scan_limit
        )
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
