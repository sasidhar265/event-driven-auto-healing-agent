import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.delivery.payloads import cloud_event
from app.delivery.retry import retry_delay
from app.models import AuditLog, Suggestion, WebhookDelivery, WebhookSubscription
from app.runtime_config import get_runtime_rules


async def deliver_due(session: AsyncSession, limit: int | None = None) -> int:
    """Deliver eligible webhooks and record success, retry, or dead-letter state."""
    delivery_config = get_runtime_rules().delivery
    limit = limit or delivery_config.webhook_batch_size
    now = datetime.now(UTC)
    deliveries = (await session.scalars(
        select(WebhookDelivery).where(
            WebhookDelivery.status.in_(["pending", "retry"]),
            WebhookDelivery.next_attempt_at <= now,
        ).order_by(WebhookDelivery.next_attempt_at).limit(limit).with_for_update(skip_locked=True)
    )).all()
    settings = get_settings()
    for delivery in deliveries:
        subscription = await session.get(WebhookSubscription, delivery.subscription_id)
        suggestion = await session.get(Suggestion, delivery.suggestion_id)
        if not subscription or not subscription.active or not suggestion:
            delivery.status = "cancelled"
            continue
        payload = cloud_event(suggestion)
        body = json.dumps(payload, separators=(",", ":"), default=str).encode()
        secret = (subscription.secret or settings.webhook_signing_secret).encode()
        signature = hmac.new(secret, body, hashlib.sha256).hexdigest()
        delivery.attempts += 1
        try:
            async with httpx.AsyncClient(timeout=settings.webhook_timeout_seconds) as client:
                response = await client.post(subscription.callback_url, content=body, headers={
                    "Content-Type": "application/cloudevents+json",
                    "Ce-Specversion": "1.0",
                    "Ce-Type": delivery_config.cloud_event_type,
                    "Ce-Id": str(suggestion.id), "X-ART-Signature-256": f"sha256={signature}",
                    "X-ART-Delivery": str(delivery.id),
                })
            delivery.response_status = response.status_code
            response.raise_for_status()
            delivery.status = "delivered"
            delivery.delivered_at = now
            delivery.last_error = None
            action = "webhook.delivered"
        except Exception as exc:
            delivery.last_error = str(exc)[
                :delivery_config.error_message_max_length
            ]
            if delivery.attempts >= settings.webhook_max_attempts:
                delivery.status = "dead_letter"
            else:
                delivery.status = "retry"
                delivery.next_attempt_at = now + timedelta(
                    seconds=retry_delay(
                        delivery.attempts,
                        delivery_config.retry_base_seconds,
                        delivery_config.retry_max_seconds,
                    )
                )
            action = f"webhook.{delivery.status}"
        session.add(AuditLog(
            tenant_id=delivery.tenant_id,
            actor=delivery_config.dispatcher_actor,
            action=action,
            resource_type="webhook_delivery", resource_id=str(delivery.id),
            details={"attempt": delivery.attempts, "response_status": delivery.response_status,
                     "suggestion_id": str(delivery.suggestion_id)},
        ))
    return len(deliveries)
