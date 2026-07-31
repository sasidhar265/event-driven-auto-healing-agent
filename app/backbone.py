"""Kafka event-backbone adapter using structured or binary CloudEvents 1.0."""

import asyncio
import base64
import json
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.config import get_settings
from app.runtime_config import get_runtime_rules
from app.security import Principal


@dataclass(frozen=True)
class BackboneEnvelope:
    cloud_event: dict[str, Any]
    principal: Principal


def _headers(values: list[tuple[str, bytes | None]] | None) -> dict[str, str]:
    return {
        key.lower(): value.decode("utf-8")
        for key, value in (values or [])
        if value is not None
    }


def decode_backbone_event(
    value: bytes, headers: list[tuple[str, bytes | None]] | None = None
) -> BackboneEnvelope:
    """Decode structured or Kafka binary-mode CloudEvents.

    Tenant identity is mandatory because all persistence is tenant scoped. A
    trusted backbone publisher supplies it as the `tenantid` extension or the
    `ce_tenantid` Kafka header.
    """

    settings = get_settings()
    kafka_headers = _headers(headers)
    try:
        body = json.loads(value)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("backbone message value must be valid JSON") from exc
    if not isinstance(body, dict):
        raise ValueError("backbone message value must be a JSON object")

    if body.get("specversion"):
        cloud_event = body
    elif kafka_headers.get("ce_specversion"):
        cloud_event = {
            "specversion": kafka_headers["ce_specversion"],
            "id": kafka_headers.get("ce_id"),
            "source": kafka_headers.get("ce_source"),
            "type": kafka_headers.get("ce_type"),
            "subject": kafka_headers.get("ce_subject"),
            "correlationid": kafka_headers.get("ce_correlationid"),
            "severity": kafka_headers.get(
                "ce_severity", settings.backbone_default_severity
            ),
            "datacontenttype": kafka_headers.get("content-type", "application/json"),
            "data": body,
        }
    else:
        raise ValueError("message is neither a structured nor binary CloudEvent")

    tenant_id = str(cloud_event.get("tenantid") or kafka_headers.get("ce_tenantid") or "").strip()
    if not tenant_id:
        raise ValueError("CloudEvent tenantid extension is required")
    actor = str(
        cloud_event.get("actor")
        or kafka_headers.get("ce_actor")
        or settings.backbone_default_actor
    )
    return BackboneEnvelope(cloud_event=cloud_event, principal=Principal(tenant_id, actor))


def dead_letter_record(
    *, value: bytes, headers: list[tuple[str, bytes | None]] | None,
    topic: str, partition: int, offset: int, error: Exception,
) -> bytes:
    """Create a JSON-safe dead-letter envelope without assuming UTF-8 input."""

    record = {
        "source": {"topic": topic, "partition": partition, "offset": offset},
        "error": {
            "type": type(error).__name__,
            "message": str(error)[
                :get_runtime_rules().delivery.error_message_max_length
            ],
        },
        "original": {
            "value_base64": base64.b64encode(value).decode("ascii"),
            "headers": _headers(headers),
        },
    }
    return json.dumps(record, separators=(",", ":")).encode()


def _kafka_security(settings: Any) -> dict[str, Any]:
    options: dict[str, Any] = {"security_protocol": settings.kafka_security_protocol}
    if settings.kafka_sasl_mechanism:
        options.update({
            "sasl_mechanism": settings.kafka_sasl_mechanism,
            "sasl_plain_username": settings.kafka_sasl_username,
            "sasl_plain_password": settings.kafka_sasl_password,
        })
    return options


async def run() -> None:
    # Imported lazily so the HTTP/database runtime can operate without loading a
    # Kafka client when the optional backbone process is not used.
    from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, TopicPartition
    from app.db import SessionLocal
    from app.ingestion import persist_cloud_event

    settings = get_settings()
    security = _kafka_security(settings)
    consumer = AIOKafkaConsumer(
        settings.kafka_input_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.kafka_consumer_group,
        client_id=f"{settings.service_name}-consumer",
        enable_auto_commit=False,
        auto_offset_reset=settings.kafka_auto_offset_reset,
        isolation_level="read_committed",
        **security,
    )
    producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        client_id=f"{settings.service_name}-dead-letter",
        **security,
    )
    await consumer.start()
    await producer.start()
    try:
        async for message in consumer:
            position = {TopicPartition(message.topic, message.partition): message.offset + 1}
            try:
                envelope = decode_backbone_event(message.value, message.headers)
                async with SessionLocal() as session:
                    await persist_cloud_event(
                        envelope.cloud_event, envelope.principal, session
                    )
            except (ValueError, ValidationError) as exc:
                record = dead_letter_record(
                    value=message.value, headers=message.headers,
                    topic=message.topic, partition=message.partition,
                    offset=message.offset, error=exc,
                )
                await producer.send_and_wait(settings.kafka_dead_letter_topic, record)
            # Commit only after durable DB ingestion or durable dead-letter
            # publication. Unexpected DB/broker errors escape and remain uncommitted.
            await consumer.commit(position)
    finally:
        await consumer.stop()
        await producer.stop()


async def main() -> None:
    from app.db import engine

    try:
        await run()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
