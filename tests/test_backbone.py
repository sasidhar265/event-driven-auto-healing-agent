import base64
import json

import pytest

from app.backbone import dead_letter_record, decode_backbone_event
from app.ingestion import cloud_event_to_event
from app.schemas import CloudEventCreate


def test_decodes_structured_cloud_event_with_tenant():
    raw = {
        "specversion": "1.0",
        "id": "failure-42",
        "source": "ci://orders",
        "type": "api.test.timeout",
        "tenantid": "acme",
        "actor": "ci-runner",
        "severity": "error",
        "correlationid": "build-7",
        "data": {"endpoint": "/orders", "status_code": 504},
    }
    envelope = decode_backbone_event(json.dumps(raw).encode())
    assert envelope.principal.tenant_id == "acme"
    assert envelope.principal.actor == "ci-runner"
    event = cloud_event_to_event(CloudEventCreate.model_validate(envelope.cloud_event))
    assert event.external_id == "failure-42"
    assert event.correlation_key == "build-7"
    assert event.payload["endpoint"] == "/orders"


def test_decodes_binary_cloud_event_headers():
    envelope = decode_backbone_event(
        b'{"failed_locator":{"strategy":"xpath","value":"//button"}}',
        [
            ("ce_specversion", b"1.0"),
            ("ce_id", b"failure-43"),
            ("ce_source", b"ci://ui"),
            ("ce_type", b"ui.xpath.element_not_found"),
            ("ce_tenantid", b"acme"),
            ("ce_severity", b"error"),
        ],
    )
    assert envelope.cloud_event["id"] == "failure-43"
    assert envelope.cloud_event["data"]["failed_locator"]["strategy"] == "xpath"


def test_rejects_event_without_tenant():
    raw = {
        "specversion": "1.0", "id": "failure-44",
        "source": "ci://orders", "type": "api.test.failed", "data": {},
    }
    with pytest.raises(ValueError, match="tenantid"):
        decode_backbone_event(json.dumps(raw).encode())


def test_dead_letter_preserves_non_utf8_payload():
    value = b"\xff\x00invalid"
    record = json.loads(dead_letter_record(
        value=value, headers=[("ce_id", b"bad-1")],
        topic="failures", partition=2, offset=9, error=ValueError("invalid event"),
    ))
    assert base64.b64decode(record["original"]["value_base64"]) == value
    assert record["source"] == {"topic": "failures", "partition": 2, "offset": 9}
