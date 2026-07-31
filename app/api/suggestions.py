"""Suggestion review, decision, and remediation-reference endpoints."""

import uuid

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers import api_settings, internal_router, operations_router
from app.db import get_session
from app.repositories.suggestions import commands as suggestion_commands
from app.repositories.suggestions import queries as suggestion_queries
from app.schemas import DecisionCreate, SuggestionRead
from app.security import Principal, principal

@operations_router.get("/suggestions", response_model=list[SuggestionRead])
async def list_suggestions(event_id: uuid.UUID | None = None, auth: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    """List tenant suggestions, optionally restricted to one source event."""
    return await suggestion_queries.list_suggestions(
        session,
        auth.tenant_id,
        api_settings.api_suggestion_limit,
        event_id,
    )


@operations_router.post("/suggestions/{suggestion_id}/decision", response_model=SuggestionRead)
async def decide(suggestion_id: uuid.UUID, body: DecisionCreate, auth: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    """Accept or reject a locked suggestion and update reusable learning records."""
    item = await suggestion_queries.get_suggestion_for_update(
        session, suggestion_id, auth.tenant_id
    )
    if not item:
        raise HTTPException(404, "Suggestion not found")

    event = await suggestion_queries.get_source_event(
        session, item.event_id, auth.tenant_id
    )
    if not event:
        raise HTTPException(404, "Source event not found")

    return await suggestion_commands.apply_decision(session, item, event, body, auth)


@internal_router.get("/references")
async def list_references(
    active_only: bool = True,
    auth: Principal = Depends(principal),
    session: AsyncSession = Depends(get_session),
):
    """List reusable remediation references for internal administrators."""
    rows = await suggestion_queries.list_references(
        session, auth.tenant_id, api_settings.api_delivery_limit, active_only
    )
    return [
        {
            "id": row.id, "event_id": row.event_id,
            "suggestion_id": row.suggestion_id, "event_type": row.event_type,
            "severity": row.severity, "fingerprint": row.fingerprint,
            "agent_type": row.agent_type, "title": row.title,
            "rationale": row.rationale, "proposed_changes": row.proposed_changes,
            "confidence": row.confidence, "outcome": row.outcome,
            "decision_reason": row.decision_reason, "active": row.active,
            "use_count": row.use_count, "last_used_at": row.last_used_at,
            "created_at": row.created_at,
        }
        for row in rows
    ]
