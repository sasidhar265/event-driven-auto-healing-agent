import pytest

from app.config import Settings
from app.integrations.postgres_bridge import (
    ExternalPostgresBridge, quote_identifier, quote_table,
)


def test_quotes_allowlisted_postgres_identifiers():
    assert quote_identifier("event_id") == '"event_id"'
    assert quote_table("operations.failure_events") == '"operations"."failure_events"'


@pytest.mark.parametrize(
    "value",
    ["events; DROP TABLE events", "public.events.extra", "event-id", "", "events payload"],
)
def test_rejects_unsafe_postgres_identifiers(value):
    with pytest.raises(ValueError):
        quote_table(value)


def test_bridge_accepts_custom_table_and_column_mapping():
    settings = Settings(
        external_postgres_enabled=True,
        external_event_table="operations.incidents",
        external_event_id_column="incident_number",
        external_event_payload_column="diagnostics",
        external_result_table="automation.recommendations",
    )
    bridge = ExternalPostgresBridge(settings)
    assert bridge.event_table == '"operations"."incidents"'
    assert bridge.columns.event_id == '"incident_number"'
    assert bridge.columns.payload == '"diagnostics"'
