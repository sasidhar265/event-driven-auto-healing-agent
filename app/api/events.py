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
from app.services.routing import FailureRouter, route_details


@operations_router.post("/events", response_model=EventRead, status_code=status.HTTP_202_ACCEPTED)
async def ingest_event(
    body: EventCreate,
    auth: Principal = Depends(principal),
    session: AsyncSession = Depends(get_session),
):
    """Accept a native incident and atomically queue it for worker processing."""
    return await persist_event(body, auth, session)


@integration_router.post(
    "/events/cloudevents", response_model=EventRead, status_code=status.HTTP_202_ACCEPTED
)
async def ingest_cloud_event(
    body: CloudEventCreate,
    auth: Principal = Depends(principal),
    session: AsyncSession = Depends(get_session),
):
    """Accept a CloudEvents 1.0 incident through the optional integration API."""
    return await persist_event(cloud_event_to_event(body), auth, session)


@operations_router.get("/events/{event_id}", response_model=EventRead)
async def get_event(
    event_id: uuid.UUID,
    auth: Principal = Depends(principal),
    session: AsyncSession = Depends(get_session),
):
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
        (record for record in audit_records if record.action == "event.classified"),
        None,
    )
    classification = dict(classification_record.details) if classification_record else {}
    recovery_record = next(
        (record for record in audit_records if record.action == "suggestion.recovery_evaluated"),
        None,
    )
    test_rerun_record = next(
        (
            record
            for record in reversed(audit_records)
            if record.action == "suggestion.test_rerun_completed"
        ),
        None,
    )
    test_rerun_status = (
        str(test_rerun_record.details.get("status", "")).upper() if test_rerun_record else None
    )
    if classification:
        current_explanation = route_details(FailureRouter().classify(event))
        classification.setdefault("category_scores", current_explanation["category_scores"])
        classification.setdefault(
            "confidence_calculation", current_explanation["confidence_calculation"]
        )
    reanalysis_record = next(
        (
            record
            for record in reversed(audit_records)
            if record.action in {"event.reanalysis_queued", "event.reanalysis_escalated"}
        ),
        None,
    )
    primary_suggestion = suggestions[-1] if suggestions else None
    confidence = primary_suggestion.confidence if primary_suggestion else None
    suggestion_status = primary_suggestion.status.value if primary_suggestion else "pending"
    suggestion_confidence_calculation = (
        primary_suggestion.policy_result.get("confidence_calculation", {})
        if primary_suggestion
        else {}
    )
    if primary_suggestion and not suggestion_confidence_calculation:
        suggestion_confidence_calculation = {
            "specialist_base": confidence,
            "policy_adjustments": [],
            "adjustment_total": 0.0,
            "before_clamp": confidence,
            "minimum": 0.0,
            "maximum": 1.0,
            "final_confidence": confidence,
            "review_threshold": api_settings.confidence_review_threshold,
            "ready_threshold": api_settings.confidence_delivery_threshold,
            "decision": suggestion_status,
            "formula": "clamp(specialist base + policy adjustments, 0, 1)",
        }

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
                "incident_fingerprint": event.payload.get("art_incident_fingerprint"),
                "normalized_context": event.payload.get("art_context", {}),
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
                classification_record.created_at if classification_record else event.processed_at
            ),
            "summary": "Structured evidence and weighted signals select the responsible specialist.",
            "api": "Worker: FailureRouter.classify",
            "data": ["audit_logs", "art.failure_events", "art.agent_run_steps"],
            "details": {
                "input_event": {
                    "event_type": event.event_type,
                    "source": event.source,
                    "severity": event.severity,
                },
                "payload_evidence": event.payload,
                **classification,
            },
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
                "business_impact": event.payload.get("art_business_impact", {}),
                **{
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
                "calculation": suggestion_confidence_calculation,
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
                "suggestion_id": (str(primary_suggestion.id) if primary_suggestion else None),
                "status": suggestion_status,
                "total_suggestions": len(suggestions),
            },
        },
        {
            "key": "test_rerun",
            "name": "Accepted-suggestion test rerun",
            "status": (test_rerun_status.lower() if test_rerun_status else "pending"),
            "timestamp": test_rerun_record.created_at if test_rerun_record else None,
            "summary": "An accepted suggestion queues its allow-listed test target for a governed pytest rerun.",
            "api": "Worker: test.rerun.requested",
            "data": [
                "outbox",
                "art.execution_intents",
                "art.execution_result_refs",
                "art.outcome_feedback",
                "audit_logs",
            ],
            "details": dict(test_rerun_record.details) if test_rerun_record else {},
        },
        {
            "key": "negative_learning",
            "name": "Negative learning and reanalysis",
            "status": (
                "escalated"
                if reanalysis_record and reanalysis_record.action == "event.reanalysis_escalated"
                else "queued"
                if reanalysis_record
                else "blocked"
                if test_rerun_status == "SKIPPED"
                else "not_required"
                if test_rerun_status == "SUCCESS"
                else "pending"
            ),
            "timestamp": reanalysis_record.created_at if reanalysis_record else None,
            "summary": "Failed reruns invalidate ineffective remediation evidence and trigger bounded alternative analysis.",
            "api": "Worker: event.reanalysis.requested",
            "data": ["remediation_references", "outbox", "audit_logs"],
            "details": (
                dict(reanalysis_record.details)
                if reanalysis_record
                else {
                    "reason": (
                        "The test did not execute, so ART has no remediation result to learn from."
                        if test_rerun_status == "SKIPPED"
                        else "The test passed; negative learning is not required."
                        if test_rerun_status == "SUCCESS"
                        else "Waiting for a failed test rerun."
                    )
                }
            ),
        },
        {
            "key": "recovery_verification",
            "name": "Recovery verification",
            "status": (
                recovery_record.details.get("status", "pending")
                if recovery_record
                else "blocked"
                if test_rerun_status in {"SKIPPED", "FAILED"}
                else "pending"
            ),
            "timestamp": recovery_record.created_at if recovery_record else None,
            "summary": "Before/after telemetry verifies whether the remediation improved service health.",
            "api": "POST /v1/suggestions/{suggestion_id}/recovery-evaluation",
            "data": ["audit_logs"],
            "details": (
                dict(recovery_record.details)
                if recovery_record
                else {
                    "reason": (
                        "Recovery verification requires a completed test and before/after telemetry."
                        if test_rerun_status == "SKIPPED"
                        else "Recovery verification cannot pass while the validation test is failing."
                        if test_rerun_status == "FAILED"
                        else "Submit before/after telemetry to evaluate recovery."
                    )
                }
            ),
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
