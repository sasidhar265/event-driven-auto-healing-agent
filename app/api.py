import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

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

router = APIRouter(prefix="/v1")


@router.post("/events", response_model=EventRead, status_code=status.HTTP_202_ACCEPTED)
async def ingest_event(body: EventCreate, auth: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    return await persist_event(body, auth, session)


@router.post("/events/cloudevents", response_model=EventRead, status_code=status.HTTP_202_ACCEPTED)
async def ingest_cloud_event(body: CloudEventCreate, auth: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    return await persist_event(cloud_event_to_event(body), auth, session)


@router.get("/events/{event_id}", response_model=EventRead)
async def get_event(event_id: uuid.UUID, auth: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    event = await session.scalar(select(Event).where(Event.id == event_id, Event.tenant_id == auth.tenant_id))
    if not event:
        raise HTTPException(404, "Event not found")
    return event


@router.get("/events", response_model=list[EventRead])
async def list_events(
    limit: int = Query(50, ge=1, le=200),
    auth: Principal = Depends(principal),
    session: AsyncSession = Depends(get_session),
):
    return list((await session.scalars(
        select(Event).where(Event.tenant_id == auth.tenant_id)
        .order_by(Event.created_at.desc()).limit(limit)
    )).all())


@router.get("/overview")
async def overview(
    auth: Principal = Depends(principal),
    session: AsyncSession = Depends(get_session),
):
    async def count(model, *criteria) -> int:
        return int(await session.scalar(
            select(func.count()).select_from(model).where(
                model.tenant_id == auth.tenant_id, *criteria
            )
        ) or 0)

    recent_events = (await session.scalars(
        select(Event).where(Event.tenant_id == auth.tenant_id)
        .order_by(Event.created_at.desc()).limit(5)
    )).all()
    return {
        "events": await count(Event),
        "processing": await count(
            Event, Event.status.in_([EventStatus.RECEIVED, EventStatus.PROCESSING])
        ),
        "suggestions": await count(Suggestion),
        "ready": await count(Suggestion, Suggestion.status == SuggestionStatus.READY),
        "review": await count(Suggestion, Suggestion.status == SuggestionStatus.REVIEW),
        "dead_letters": await count(WebhookDelivery, WebhookDelivery.status == "dead_letter"),
        "recent_events": [
            {
                "id": row.id, "external_id": row.external_id,
                "event_type": row.event_type, "severity": row.severity,
                "status": row.status, "created_at": row.created_at,
            }
            for row in recent_events
        ],
    }


@router.get("/suggestions", response_model=list[SuggestionRead])
async def list_suggestions(event_id: uuid.UUID | None = None, auth: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    query = select(Suggestion).where(Suggestion.tenant_id == auth.tenant_id).order_by(Suggestion.created_at.desc())
    if event_id:
        query = query.where(Suggestion.event_id == event_id)
    return list((await session.scalars(query.limit(100))).all())


@router.post("/suggestions/{suggestion_id}/decision", response_model=SuggestionRead)
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


@router.get("/references")
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
        query.order_by(RemediationReference.created_at.desc()).limit(200)
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


@router.post("/policies", status_code=201)
async def create_policy(body: PolicyCreate, auth: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    policy = Policy(tenant_id=auth.tenant_id, **body.model_dump())
    session.add(policy)
    await session.commit()
    return {"id": policy.id, "version": policy.version}


@router.get("/policies")
async def list_policies(
    auth: Principal = Depends(principal),
    session: AsyncSession = Depends(get_session),
):
    rows = (await session.scalars(
        select(Policy).where(Policy.tenant_id == auth.tenant_id)
        .order_by(Policy.created_at.desc()).limit(100)
    )).all()
    return [
        {
            "id": row.id, "name": row.name, "rules": row.rules,
            "active": row.active, "version": row.version, "created_at": row.created_at,
        }
        for row in rows
    ]


@router.post("/knowledge", status_code=201)
async def create_knowledge(body: KnowledgeCreate, auth: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    data = body.model_dump()
    metadata = data.pop("metadata")
    item = KnowledgeItem(tenant_id=auth.tenant_id, metadata_=metadata, **data)
    session.add(item)
    await session.commit()
    return {"id": item.id}


@router.get("/knowledge")
async def list_knowledge(
    auth: Principal = Depends(principal),
    session: AsyncSession = Depends(get_session),
):
    rows = (await session.scalars(
        select(KnowledgeItem).where(KnowledgeItem.tenant_id == auth.tenant_id)
        .order_by(KnowledgeItem.created_at.desc()).limit(100)
    )).all()
    return [
        {
            "id": row.id, "title": row.title, "content": row.content,
            "tags": row.tags, "metadata": row.metadata_, "created_at": row.created_at,
        }
        for row in rows
    ]


@router.post("/subscriptions", response_model=SubscriptionRead, status_code=201)
async def create_subscription(body: SubscriptionCreate, auth: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    item = WebhookSubscription(tenant_id=auth.tenant_id, **body.model_dump())
    session.add(item)
    await session.flush()
    session.add(AuditLog(tenant_id=auth.tenant_id, actor=auth.actor, action="subscription.created", resource_type="webhook_subscription", resource_id=str(item.id), details={"callback_url": item.callback_url, "event_types": item.event_types}))
    await session.commit()
    await session.refresh(item)
    return item


@router.get("/subscriptions", response_model=list[SubscriptionRead])
async def list_subscriptions(auth: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    return list((await session.scalars(select(WebhookSubscription).where(
        WebhookSubscription.tenant_id == auth.tenant_id
    ).order_by(WebhookSubscription.created_at.desc()))).all())


@router.delete("/subscriptions/{subscription_id}", status_code=204)
async def deactivate_subscription(subscription_id: uuid.UUID, auth: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    item = await session.scalar(select(WebhookSubscription).where(
        WebhookSubscription.id == subscription_id, WebhookSubscription.tenant_id == auth.tenant_id
    ).with_for_update())
    if not item:
        raise HTTPException(404, "Subscription not found")
    item.active = False
    session.add(AuditLog(tenant_id=auth.tenant_id, actor=auth.actor, action="subscription.deactivated", resource_type="webhook_subscription", resource_id=str(item.id), details={}))
    await session.commit()


@router.get("/deliveries")
async def list_deliveries(suggestion_id: uuid.UUID | None = None, auth: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    query = select(WebhookDelivery).where(WebhookDelivery.tenant_id == auth.tenant_id)
    if suggestion_id:
        query = query.where(WebhookDelivery.suggestion_id == suggestion_id)
    rows = (await session.scalars(query.order_by(WebhookDelivery.created_at.desc()).limit(200))).all()
    return [{"id": row.id, "subscription_id": row.subscription_id, "suggestion_id": row.suggestion_id,
             "status": row.status, "attempts": row.attempts, "response_status": row.response_status,
             "last_error": row.last_error, "next_attempt_at": row.next_attempt_at,
             "delivered_at": row.delivered_at, "created_at": row.created_at} for row in rows]


@router.post("/deliveries/{delivery_id}/retry", status_code=202)
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


@router.get("/audit")
async def audit(limit: int = Query(100, ge=1, le=500), auth: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    rows = (await session.scalars(select(AuditLog).where(AuditLog.tenant_id == auth.tenant_id).order_by(AuditLog.created_at.desc()).limit(limit))).all()
    return [{"id": row.id, "actor": row.actor, "action": row.action, "resource_type": row.resource_type, "resource_id": row.resource_id, "details": row.details, "created_at": row.created_at} for row in rows]
