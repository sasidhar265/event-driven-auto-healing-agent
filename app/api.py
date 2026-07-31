import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.decisions import record_suggestion_decision
from app.ingestion import cloud_event_to_event, persist_event
from app.models import (
    AuditLog, Event, EventStatus, KnowledgeItem, Policy, RemediationReference,
    Suggestion, SuggestionStatus, WebhookDelivery, WebhookSubscription,
)
from app.schemas import (
    CloudEventCreate, DecisionCreate, EventCreate, EventRead, KnowledgeCreate, PolicyCreate,
    SubscriptionCreate, SubscriptionRead, SuggestionRead,
)
from app.security import Principal, principal

operations_router = APIRouter(prefix="/v1")
integration_router = APIRouter(prefix="/v1")
internal_router = APIRouter(prefix="/v1/internal", tags=["Internal services"])
router = operations_router
api_settings = get_settings()


@operations_router.post("/events", response_model=EventRead, status_code=status.HTTP_202_ACCEPTED)
async def ingest_event(body: EventCreate, auth: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    return await persist_event(body, auth, session)


@integration_router.post("/events/cloudevents", response_model=EventRead, status_code=status.HTTP_202_ACCEPTED)
async def ingest_cloud_event(body: CloudEventCreate, auth: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    return await persist_event(cloud_event_to_event(body), auth, session)


@operations_router.get("/events/{event_id}", response_model=EventRead)
async def get_event(event_id: uuid.UUID, auth: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    event = await session.scalar(select(Event).where(Event.id == event_id, Event.tenant_id == auth.tenant_id))
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

    event = await session.scalar(
        select(Event).where(
            Event.id == event_id,
            Event.tenant_id == auth.tenant_id,
        )
    )
    if not event:
        raise HTTPException(404, "Event not found")

    suggestions = list(
        (
            await session.scalars(
                select(Suggestion)
                .where(
                    Suggestion.event_id == event.id,
                    Suggestion.tenant_id == auth.tenant_id,
                )
                .order_by(Suggestion.created_at)
            )
        ).all()
    )
    audit_records = list(
        (
            await session.scalars(
                select(AuditLog)
                .where(
                    AuditLog.tenant_id == auth.tenant_id,
                    AuditLog.resource_type == "event",
                    AuditLog.resource_id == str(event.id),
                )
                .order_by(AuditLog.created_at)
            )
        ).all()
    )

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
    return list((await session.scalars(
        select(Event).where(Event.tenant_id == auth.tenant_id)
        .order_by(Event.created_at.desc()).limit(limit)
    )).all())


@operations_router.get("/overview")
async def overview(
    environment: str | None = Query(default=None, pattern="^(dev|test|preprod|prod)$"),
    auth: Principal = Depends(principal),
    session: AsyncSession = Depends(get_session),
):
    async def count(model, *criteria) -> int:
        return int(await session.scalar(
            select(func.count()).select_from(model).where(
                model.tenant_id == auth.tenant_id, *criteria
            )
        ) or 0)

    recent_query = select(Event).where(Event.tenant_id == auth.tenant_id)
    if environment:
        recent_query = recent_query.where(
            Event.payload["environment"].astext == environment
        )
    recent_events = (
        await session.scalars(
            recent_query.order_by(Event.created_at.desc())
            .limit(api_settings.api_recent_event_limit)
        )
    ).all()
    suggestion_query = (
        select(
            Suggestion.id,
            Suggestion.title,
            Suggestion.confidence,
            Suggestion.policy_result,
            Suggestion.status,
            Suggestion.created_at,
            Event.external_id,
            Event.correlation_key,
        )
        .join(Event, Event.id == Suggestion.event_id)
        .where(
            Suggestion.tenant_id == auth.tenant_id,
            Event.tenant_id == auth.tenant_id,
        )
    )
    if environment:
        suggestion_query = suggestion_query.where(
            Event.payload["environment"].astext == environment
        )
    suggestion_rows = (await session.execute(suggestion_query)).all()
    thresholds = get_settings()
    confidence_counts = {"suppressed": 0, "review": 0, "ready": 0}
    decision_records = []
    for (
        suggestion_id,
        title,
        confidence,
        policy_result,
        recorded_status,
        created_at,
        failure_id,
        correlation_id,
    ) in suggestion_rows:
        policy_result = policy_result or {}
        if policy_result.get("violations"):
            classification = "suppressed"
        elif (
            policy_result.get("approvals")
            or confidence < thresholds.confidence_delivery_threshold
        ):
            classification = (
                "review"
                if confidence >= thresholds.confidence_review_threshold
                else "suppressed"
            )
        else:
            classification = "ready"
        confidence_counts[classification] += 1
        decision_records.append({
            "suggestion_id": suggestion_id,
            "title": title,
            "confidence": confidence,
            "classification": classification,
            "recorded_status": recorded_status,
            "failure_id": failure_id,
            "correlation_id": correlation_id,
            "created_at": created_at,
        })
    decision_records.sort(key=lambda item: item["confidence"], reverse=True)

    return {
        "events": await count(Event),
        "processing": await count(
            Event, Event.status.in_([EventStatus.RECEIVED, EventStatus.PROCESSING])
        ),
        "suggestions": await count(Suggestion),
        "ready": await count(Suggestion, Suggestion.status == SuggestionStatus.READY),
        "review": await count(Suggestion, Suggestion.status == SuggestionStatus.REVIEW),
        "decision_model": {
            "thresholds": {
                "review": thresholds.confidence_review_threshold,
                "ready": thresholds.confidence_delivery_threshold,
            },
            "counts": confidence_counts,
            "total": len(suggestion_rows),
            "records": decision_records,
        },
        "dead_letters": await count(WebhookDelivery, WebhookDelivery.status == "dead_letter"),
        "recent_events": [
            {
                "id": row.id, "external_id": row.external_id,
                "event_type": row.event_type, "source": row.source,
                "environment": row.payload.get("environment", "unknown"),
                "severity": row.severity,
                "status": row.status, "created_at": row.created_at,
            }
            for row in recent_events
        ],
    }


@operations_router.get("/suggestions", response_model=list[SuggestionRead])
async def list_suggestions(event_id: uuid.UUID | None = None, auth: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    query = select(Suggestion).where(Suggestion.tenant_id == auth.tenant_id).order_by(Suggestion.created_at.desc())
    if event_id:
        query = query.where(Suggestion.event_id == event_id)
    return list(
        (
            await session.scalars(query.limit(api_settings.api_suggestion_limit))
        ).all()
    )


@operations_router.post("/suggestions/{suggestion_id}/decision", response_model=SuggestionRead)
async def decide(suggestion_id: uuid.UUID, body: DecisionCreate, auth: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    item = await session.scalar(
        select(Suggestion)
        .where(
            Suggestion.id == suggestion_id,
            Suggestion.tenant_id == auth.tenant_id,
        )
        .with_for_update()
    )
    if not item:
        raise HTTPException(404, "Suggestion not found")

    event = await session.scalar(
        select(Event).where(
            Event.id == item.event_id,
            Event.tenant_id == auth.tenant_id,
        )
    )
    if not event:
        raise HTTPException(404, "Source event not found")

    await record_suggestion_decision(session, item, event, body, auth)
    await session.commit()
    await session.refresh(item)
    return item


@internal_router.get("/references")
async def list_references(
    active_only: bool = True,
    auth: Principal = Depends(principal),
    session: AsyncSession = Depends(get_session),
):
    query = select(RemediationReference).where(
        RemediationReference.tenant_id == auth.tenant_id
    )
    if active_only:
        query = query.where(RemediationReference.active.is_(True))
    rows = (await session.scalars(
        query.order_by(RemediationReference.created_at.desc())
        .limit(api_settings.api_delivery_limit)
    )).all()
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


@internal_router.post("/policies", status_code=201)
async def create_policy(body: PolicyCreate, auth: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    policy = Policy(tenant_id=auth.tenant_id, **body.model_dump())
    session.add(policy)
    await session.commit()
    return {"id": policy.id, "version": policy.version}


@internal_router.get("/policies")
async def list_policies(
    auth: Principal = Depends(principal),
    session: AsyncSession = Depends(get_session),
):
    rows = (await session.scalars(
        select(Policy).where(Policy.tenant_id == auth.tenant_id)
        .order_by(Policy.created_at.desc()).limit(api_settings.api_admin_limit)
    )).all()
    return [
        {
            "id": row.id, "name": row.name, "rules": row.rules,
            "active": row.active, "version": row.version, "created_at": row.created_at,
        }
        for row in rows
    ]


@internal_router.post("/knowledge", status_code=201)
async def create_knowledge(body: KnowledgeCreate, auth: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    data = body.model_dump()
    metadata = data.pop("metadata")
    item = KnowledgeItem(tenant_id=auth.tenant_id, metadata_=metadata, **data)
    session.add(item)
    await session.commit()
    return {"id": item.id}


@internal_router.get("/knowledge")
async def list_knowledge(
    auth: Principal = Depends(principal),
    session: AsyncSession = Depends(get_session),
):
    rows = (await session.scalars(
        select(KnowledgeItem).where(KnowledgeItem.tenant_id == auth.tenant_id)
        .order_by(KnowledgeItem.created_at.desc())
        .limit(api_settings.api_admin_limit)
    )).all()
    return [
        {
            "id": row.id, "title": row.title, "content": row.content,
            "tags": row.tags, "metadata": row.metadata_, "created_at": row.created_at,
        }
        for row in rows
    ]


@integration_router.post("/subscriptions", response_model=SubscriptionRead, status_code=201)
async def create_subscription(body: SubscriptionCreate, auth: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    item = WebhookSubscription(tenant_id=auth.tenant_id, **body.model_dump())
    session.add(item)
    await session.flush()
    session.add(AuditLog(tenant_id=auth.tenant_id, actor=auth.actor, action="subscription.created", resource_type="webhook_subscription", resource_id=str(item.id), details={"callback_url": item.callback_url, "event_types": item.event_types}))
    await session.commit()
    await session.refresh(item)
    return item


@integration_router.get("/subscriptions", response_model=list[SubscriptionRead])
async def list_subscriptions(auth: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    return list((await session.scalars(select(WebhookSubscription).where(
        WebhookSubscription.tenant_id == auth.tenant_id
    ).order_by(WebhookSubscription.created_at.desc()))).all())


@integration_router.delete("/subscriptions/{subscription_id}", status_code=204)
async def deactivate_subscription(subscription_id: uuid.UUID, auth: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    item = await session.scalar(select(WebhookSubscription).where(
        WebhookSubscription.id == subscription_id, WebhookSubscription.tenant_id == auth.tenant_id
    ).with_for_update())
    if not item:
        raise HTTPException(404, "Subscription not found")
    item.active = False
    session.add(AuditLog(tenant_id=auth.tenant_id, actor=auth.actor, action="subscription.deactivated", resource_type="webhook_subscription", resource_id=str(item.id), details={}))
    await session.commit()


@integration_router.get("/deliveries")
async def list_deliveries(suggestion_id: uuid.UUID | None = None, auth: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    query = select(WebhookDelivery).where(WebhookDelivery.tenant_id == auth.tenant_id)
    if suggestion_id:
        query = query.where(WebhookDelivery.suggestion_id == suggestion_id)
    rows = (
        await session.scalars(
            query.order_by(WebhookDelivery.created_at.desc())
            .limit(api_settings.api_delivery_limit)
        )
    ).all()
    return [{"id": row.id, "subscription_id": row.subscription_id, "suggestion_id": row.suggestion_id,
             "status": row.status, "attempts": row.attempts, "response_status": row.response_status,
             "last_error": row.last_error, "next_attempt_at": row.next_attempt_at,
             "delivered_at": row.delivered_at, "created_at": row.created_at} for row in rows]


@integration_router.post("/deliveries/{delivery_id}/retry", status_code=202)
async def retry_delivery(delivery_id: uuid.UUID, auth: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    item = await session.scalar(select(WebhookDelivery).where(
        WebhookDelivery.id == delivery_id, WebhookDelivery.tenant_id == auth.tenant_id
    ).with_for_update())
    if not item:
        raise HTTPException(404, "Delivery not found")
    from datetime import UTC, datetime
    item.status, item.next_attempt_at, item.last_error = "retry", datetime.now(UTC), None
    session.add(AuditLog(tenant_id=auth.tenant_id, actor=auth.actor, action="webhook.retry_requested", resource_type="webhook_delivery", resource_id=str(item.id), details={}))
    await session.commit()
    return {"id": item.id, "status": item.status}


@operations_router.get("/audit")
async def audit(
    limit: int = Query(
        api_settings.api_default_limit,
        ge=1,
        le=api_settings.api_max_limit,
    ),
    environment: str | None = Query(default=None, pattern="^(dev|test|preprod|prod)$"),
    from_time: datetime | None = None,
    to_time: datetime | None = None,
    correlation_id: str | None = Query(default=None, max_length=300),
    auth: Principal = Depends(principal),
    session: AsyncSession = Depends(get_session),
):
    query = select(AuditLog).where(AuditLog.tenant_id == auth.tenant_id)
    if from_time:
        query = query.where(AuditLog.created_at >= from_time)
    if to_time:
        query = query.where(AuditLog.created_at <= to_time)
    normalized_correlation_id = correlation_id.strip() if correlation_id else None
    if environment or normalized_correlation_id:
        event_filters = [Event.tenant_id == auth.tenant_id]
        if environment:
            event_filters.append(Event.payload["environment"].astext == environment)
        if normalized_correlation_id:
            event_filters.append(Event.correlation_key.ilike(f"%{normalized_correlation_id}%"))

        environment_events = select(cast(Event.id, String)).where(*event_filters)
        environment_suggestions = (
            select(cast(Suggestion.id, String))
            .join(Event, Event.id == Suggestion.event_id)
            .where(
                Suggestion.tenant_id == auth.tenant_id,
                *event_filters,
            )
        )
        query = query.where(
            or_(
                and_(
                    AuditLog.resource_type == "event",
                    AuditLog.resource_id.in_(environment_events),
                ),
                and_(
                    AuditLog.resource_type == "suggestion",
                    AuditLog.resource_id.in_(environment_suggestions),
                ),
            )
        )
    rows = (
        await session.scalars(query.order_by(AuditLog.created_at.desc()).limit(limit))
    ).all()

    event_resource_ids = [
        row.resource_id for row in rows if row.resource_type == "event"
    ]
    suggestion_resource_ids = [
        row.resource_id for row in rows if row.resource_type == "suggestion"
    ]
    event_identifiers = {}
    if event_resource_ids:
        event_rows = await session.execute(
            select(Event.id, Event.correlation_key, Event.external_id).where(
                Event.tenant_id == auth.tenant_id,
                cast(Event.id, String).in_(event_resource_ids),
            )
        )
        event_identifiers.update(
            {
                str(event_id): {
                    "correlation_id": correlation_key,
                    "failure_id": external_id,
                }
                for event_id, correlation_key, external_id in event_rows
            }
        )
    if suggestion_resource_ids:
        suggestion_rows = await session.execute(
            select(
                Suggestion.id,
                Event.correlation_key,
                Event.external_id,
            )
            .join(Event, Event.id == Suggestion.event_id)
            .where(
                Suggestion.tenant_id == auth.tenant_id,
                Event.tenant_id == auth.tenant_id,
                cast(Suggestion.id, String).in_(suggestion_resource_ids),
            )
        )
        event_identifiers.update(
            {
                str(suggestion_id): {
                    "correlation_id": correlation_key,
                    "failure_id": external_id,
                }
                for suggestion_id, correlation_key, external_id in suggestion_rows
            }
        )

    return [
        {
            "id": row.id,
            "actor": row.actor,
            "action": row.action,
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            **event_identifiers.get(row.resource_id, {
                "correlation_id": None,
                "failure_id": None,
            }),
            "details": row.details,
            "created_at": row.created_at,
        }
        for row in rows
    ]
