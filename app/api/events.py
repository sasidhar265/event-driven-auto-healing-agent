"""Incident intake, retrieval, trace, and listing endpoints."""

import uuid

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers import api_settings, integration_router, operations_router
from app.db import get_session
from app.ingestion import cloud_event_to_event, persist_event
from app.models import EventStatus
from app.repositories.events import queries as event_queries
from app.schemas import CloudEventCreate, EventCreate, EventRead
from app.security import Principal, principal

@operations_router.post("/events", response_model=EventRead, status_code=status.HTTP_202_ACCEPTED)
async def ingest_event(body: EventCreate, auth: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    """Accept a native incident and atomically queue it for worker processing."""
    return await persist_event(body, auth, session)


@integration_router.post("/events/cloudevents", response_model=EventRead, status_code=status.HTTP_202_ACCEPTED)
async def ingest_cloud_event(body: CloudEventCreate, auth: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    """Accept a CloudEvents 1.0 incident through the optional integration API."""
    return await persist_event(cloud_event_to_event(body), auth, session)


@operations_router.get("/events/{event_id}", response_model=EventRead)
async def get_event(event_id: uuid.UUID, auth: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    """Return one event only when it belongs to the authenticated tenant."""
    event = await event_queries.get_event(session, event_id, auth.tenant_id)
    if not event:
        raise HTTPException(404, "Event not found")
    return event


@operations_router.get("/events/{event_id}/trace")
async def get_event_trace(
    event_id: uuid.UUID,
    auth: Principal = Depends(principal),
    session: AsyncSession = Depends(get_session),
):
    """Return the persisted processing story for one tenant-scoped event."""

    event, suggestions, audit_records = await event_queries.get_trace_records(
        session, event_id, auth.tenant_id
    )
    if not event:
        raise HTTPException(404, "Event not found")

    classification_record = next(
        (
            record
            for record in audit_records
            if record.action == "event.classified"
        ),
        None,
    )
    classification = classification_record.details if classification_record else {}
    primary_suggestion = suggestions[0] if suggestions else None
    confidence = primary_suggestion.confidence if primary_suggestion else None
    suggestion_status = (
        primary_suggestion.status.value if primary_suggestion else "pending"
    )

    stages = [
        {
            "key": "ingestion",
            "name": "Event ingestion",
            "status": "completed",
            "timestamp": event.created_at,
            "summary": "The incident was validated and persisted atomically.",
            "api": "POST /v1/events or POST /v1/events/cloudevents",
            "data": ["events", "outbox", "audit_logs"],
            "details": {
                "external_id": event.external_id,
                "event_type": event.event_type,
                "correlation_id": event.correlation_key,
            },
        },
        {
            "key": "identification",
            "name": "Source identification",
            "status": "completed",
            "timestamp": event.created_at,
            "summary": "The runtime identified where and in which environment the incident occurred.",
            "api": "GET /v1/events/{event_id}",
            "data": ["events.source", "events.payload.environment"],
            "details": {
                "identified_by": event.source,
                "environment": event.payload.get("environment", "unknown"),
                "severity": event.severity,
            },
        },
        {
            "key": "classification",
            "name": "Failure classification",
            "status": "completed" if classification else "pending",
            "timestamp": (
                classification_record.created_at
                if classification_record
                else event.processed_at
            ),
            "summary": "Structured evidence and weighted signals select the responsible specialist.",
            "api": "Worker: FailureRouter.classify",
            "data": ["audit_logs", "art.failure_events", "art.agent_run_steps"],
            "details": classification,
        },
        {
            "key": "change_detection",
            "name": "Change and impact context",
            "status": "completed" if event.status == EventStatus.COMPLETED else "processing",
            "timestamp": event.processed_at,
            "summary": "The runtime extracts the affected code, test, component, endpoint, or infrastructure target.",
            "api": "Worker: specialist routing and ART lifecycle",
            "data": ["events.payload", "art.impact_assessments", "art.impact_dependencies"],
            "details": {
                key: event.payload.get(key)
                for key in (
                    "source_file",
                    "method_name",
                    "test_file",
                    "test_name",
                    "endpoint",
                    "resource_name",
                    "dependency_name",
                )
                if event.payload.get(key) is not None
            },
        },
        {
            "key": "suggestion",
            "name": "Specialist suggestion",
            "status": "completed" if primary_suggestion else "pending",
            "timestamp": (
                primary_suggestion.created_at if primary_suggestion else event.processed_at
            ),
            "summary": "The selected specialist proposes a targeted, explainable remediation.",
            "api": "GET /v1/suggestions?event_id={event_id}",
            "data": ["suggestions", "art.agent_decision_journals", "art.self_heal_proposals"],
            "details": {
                "agent": primary_suggestion.agent_type if primary_suggestion else None,
                "title": primary_suggestion.title if primary_suggestion else None,
                "rationale": primary_suggestion.rationale if primary_suggestion else None,
                "proposed_changes": (
                    primary_suggestion.proposed_changes if primary_suggestion else {}
                ),
            },
        },
        {
            "key": "confidence",
            "name": "Confidence gate",
            "status": "completed" if confidence is not None else "pending",
            "timestamp": (
                primary_suggestion.created_at if primary_suggestion else event.processed_at
            ),
            "summary": (
                f"Below {api_settings.confidence_review_threshold:.2f} is suppressed, "
                f"{api_settings.confidence_review_threshold:.2f} up to "
                f"{api_settings.confidence_delivery_threshold:.2f} requires review, "
                f"and {api_settings.confidence_delivery_threshold:.2f}+ is ready."
            ),
            "api": "ART confidence evaluator",
            "data": ["suggestions.confidence", "suggestions.status"],
            "details": {
                "score": confidence,
                "score_percent": round(confidence * 100, 1) if confidence is not None else None,
                "decision": suggestion_status,
            },
        },
        {
            "key": "outcome",
            "name": "Suggestion disposition",
            "status": suggestion_status,
            "timestamp": (
                primary_suggestion.created_at if primary_suggestion else event.processed_at
            ),
            "summary": "The ART suggestion is available for operator review or downstream delivery.",
            "api": "POST /v1/suggestions/{suggestion_id}/decision",
            "data": ["suggestions", "suggestion_decisions", "audit_logs"],
            "details": {
                "suggestion_id": (
                    str(primary_suggestion.id) if primary_suggestion else None
                ),
                "status": suggestion_status,
                "total_suggestions": len(suggestions),
            },
        },
    ]
    return {
        "event_id": event.id,
        "correlation_id": event.correlation_key,
        "tenant_id": event.tenant_id,
        "environment": event.payload.get("environment", "unknown"),
        "event_status": event.status,
        "stages": stages,
    }


@operations_router.get("/events", response_model=list[EventRead])
async def list_events(
    limit: int = Query(
        api_settings.api_event_limit,
        ge=1,
        le=api_settings.api_max_limit,
    ),
    auth: Principal = Depends(principal),
    session: AsyncSession = Depends(get_session),
):
    """List the authenticated tenant's newest events up to the validated limit."""
    return await event_queries.list_events(session, auth.tenant_id, limit)
