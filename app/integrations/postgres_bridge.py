"""Configuration-driven bridge for existing PostgreSQL event/result tables."""

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.config import Settings
from app.ingestion import persist_event
from app.models import (
    Event, IntegrationIngestion, IntegrationPublication, Suggestion, SuggestionStatus,
)
from app.schemas import EventCreate
from app.security import Principal


IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def quote_identifier(value: str) -> str:
    if not IDENTIFIER.fullmatch(value):
        raise ValueError(f"invalid PostgreSQL identifier: {value!r}")
    return f'"{value}"'


def quote_table(value: str) -> str:
    parts = value.split(".")
    if len(parts) not in (1, 2):
        raise ValueError(f"table must be 'table' or 'schema.table': {value!r}")
    return ".".join(quote_identifier(part) for part in parts)


@dataclass(frozen=True)
class BridgeColumns:
    event_id: str
    event_type: str
    source: str
    severity: str
    correlation: str
    payload: str
    tenant: str
    actor: str
    created: str
    processed: str


class ExternalPostgresBridge:
    """Poll and write only explicitly configured PostgreSQL tables/columns."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.event_table = quote_table(settings.external_event_table)
        self.result_table = quote_table(settings.external_result_table)
        self.columns = BridgeColumns(
            *[
                quote_identifier(value)
                for value in (
                    settings.external_event_id_column,
                    settings.external_event_type_column,
                    settings.external_event_source_column,
                    settings.external_event_severity_column,
                    settings.external_event_correlation_column,
                    settings.external_event_payload_column,
                    settings.external_event_tenant_column,
                    settings.external_event_actor_column,
                    settings.external_event_created_column,
                    settings.external_event_processed_column,
                )
            ]
        )
        self.engine: AsyncEngine | None = None
        self.sessions: async_sessionmaker | None = None
        self._validate_result_identifiers()

    def _validate_result_identifiers(self) -> None:
        names = [
            self.settings.external_result_suggestion_id_column,
            self.settings.external_result_event_id_column,
            self.settings.external_result_status_column,
            self.settings.external_result_confidence_column,
            self.settings.external_result_agent_column,
            self.settings.external_result_payload_column,
            self.settings.external_result_created_column,
            self.settings.external_event_result_column,
            self.settings.external_event_result_status_column,
        ]
        for name in names:
            quote_identifier(name)

    def _ensure_sessions(self) -> async_sessionmaker:
        if self.engine is None:
            url = self.settings.external_postgres_url or self.settings.database_url
            self.engine = create_async_engine(url, pool_pre_ping=True)
            self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        assert self.sessions is not None
        return self.sessions

    async def validate(self) -> dict[str, Any]:
        """Verify configured tables and columns without changing data."""

        required_event = [
            self.settings.external_event_id_column,
            self.settings.external_event_type_column,
            self.settings.external_event_source_column,
            self.settings.external_event_severity_column,
            self.settings.external_event_correlation_column,
            self.settings.external_event_payload_column,
            self.settings.external_event_tenant_column,
            self.settings.external_event_actor_column,
            self.settings.external_event_created_column,
            self.settings.external_event_processed_column,
        ]
        event_schema, event_table = self._table_parts(self.settings.external_event_table)
        found_event = await self._columns(event_schema, event_table)
        missing_event = sorted(set(required_event) - found_event)
        missing_result: list[str] = []
        if self.settings.external_result_mode == "insert":
            result_schema, result_table = self._table_parts(self.settings.external_result_table)
            found_result = await self._columns(result_schema, result_table)
            required_result = {
                self.settings.external_result_suggestion_id_column,
                self.settings.external_result_event_id_column,
                self.settings.external_result_status_column,
                self.settings.external_result_confidence_column,
                self.settings.external_result_agent_column,
                self.settings.external_result_payload_column,
                self.settings.external_result_created_column,
            }
            missing_result = sorted(required_result - found_result)
        else:
            missing_result = sorted({
                self.settings.external_event_result_column,
                self.settings.external_event_result_status_column,
            } - found_event)
        return {
            "valid": not missing_event and not missing_result,
            "event_table": self.settings.external_event_table,
            "result_mode": self.settings.external_result_mode,
            "result_table": (
                self.settings.external_result_table
                if self.settings.external_result_mode == "insert" else None
            ),
            "missing_event_columns": missing_event,
            "missing_result_columns": missing_result,
        }

    async def _columns(self, schema: str, table: str) -> set[str]:
        async with self._ensure_sessions()() as session:
            rows = await session.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = :schema AND table_name = :table
            """), {"schema": schema, "table": table})
            return {str(row[0]) for row in rows}

    @staticmethod
    def _table_parts(value: str) -> tuple[str, str]:
        parts = value.split(".")
        return (parts[0], parts[1]) if len(parts) == 2 else ("public", parts[0])

    async def pull_events(self) -> int:
        from app.db import SessionLocal

        source_key = f"postgres:{self.settings.external_event_table}"
        c = self.columns
        query = text(f"""
            SELECT {c.event_id} AS external_id, {c.event_type} AS event_type,
                   {c.source} AS source, {c.severity} AS severity,
                   {c.correlation} AS correlation_key, {c.payload} AS payload,
                   {c.tenant} AS tenant_id, {c.actor} AS actor
            FROM {self.event_table}
            WHERE {c.processed} IS NULL
            ORDER BY {c.created}
            LIMIT :limit
            FOR UPDATE SKIP LOCKED
        """)
        count = 0
        async with self._ensure_sessions()() as external:
            rows = (await external.execute(
                query, {"limit": self.settings.external_batch_size}
            )).mappings().all()
            for row in rows:
                event = EventCreate(
                    external_id=str(row["external_id"]),
                    event_type=str(row["event_type"]),
                    source=str(row["source"]),
                    severity=str(row["severity"]).lower(),
                    correlation_key=str(row["correlation_key"]),
                    payload=self._payload(row["payload"]),
                )
                async with SessionLocal() as internal:
                    stored = await persist_event(
                        event,
                        Principal(str(row["tenant_id"]), str(row["actor"] or "postgres-bridge")),
                        internal,
                    )
                async with SessionLocal() as internal:
                    existing = await internal.scalar(select(IntegrationIngestion).where(
                        IntegrationIngestion.event_id == stored.id,
                        IntegrationIngestion.source == source_key,
                    ))
                    if not existing:
                        internal.add(IntegrationIngestion(
                            event_id=stored.id, source=source_key,
                            external_id=str(row["external_id"]),
                        ))
                        await internal.commit()
                await external.execute(
                    text(f"""
                        UPDATE {self.event_table}
                        SET {c.processed} = :processed
                        WHERE {c.event_id} = :external_id AND {c.processed} IS NULL
                    """),
                    {"processed": datetime.now(UTC), "external_id": row["external_id"]},
                )
                count += 1
            await external.commit()
        return count

    @staticmethod
    def _payload(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        raise ValueError("external event payload must be a JSON object")

    async def push_ready_suggestions(self) -> int:
        from app.db import SessionLocal

        target = (
            f"postgres:insert:{self.settings.external_result_table}"
            if self.settings.external_result_mode == "insert"
            else f"postgres:update:{self.settings.external_event_table}"
        )
        source_key = f"postgres:{self.settings.external_event_table}"
        async with SessionLocal() as internal:
            rows = (await internal.execute(
                select(Suggestion, Event.external_id)
                .join(Event, Event.id == Suggestion.event_id)
                .join(
                    IntegrationIngestion,
                    (IntegrationIngestion.event_id == Event.id)
                    & (IntegrationIngestion.source == source_key),
                )
                .outerjoin(
                    IntegrationPublication,
                    (IntegrationPublication.suggestion_id == Suggestion.id)
                    & (IntegrationPublication.target == target),
                )
                .where(Suggestion.status == SuggestionStatus.READY)
                .where(IntegrationPublication.id.is_(None))
                .order_by(Suggestion.created_at.desc())
                .limit(self.settings.external_batch_size)
            )).all()
        count = 0
        async with self._ensure_sessions()() as external:
            for suggestion, external_id in rows:
                payload = json.dumps({
                    "suggestion_id": str(suggestion.id),
                    "event_id": str(suggestion.event_id),
                    "agent_type": suggestion.agent_type,
                    "title": suggestion.title,
                    "rationale": suggestion.rationale,
                    "proposed_changes": suggestion.proposed_changes,
                    "evidence": suggestion.evidence,
                    "confidence": suggestion.confidence,
                    "policy_result": suggestion.policy_result,
                    "status": suggestion.status.value,
                }, default=str)
                if self.settings.external_result_mode == "insert":
                    await self._insert_result(external, suggestion, str(external_id), payload)
                else:
                    await self._update_event(
                        external, suggestion, str(external_id), payload
                    )
                count += 1
            await external.commit()
        if rows:
            async with SessionLocal() as internal:
                internal.add_all([
                    IntegrationPublication(suggestion_id=suggestion.id, target=target)
                    for suggestion, _ in rows
                ])
                await internal.commit()
        return count

    async def _insert_result(
        self, session: Any, suggestion: Suggestion, external_id: str, payload: str
    ) -> None:
        s = self.settings
        columns = [
            s.external_result_suggestion_id_column, s.external_result_event_id_column,
            s.external_result_status_column, s.external_result_confidence_column,
            s.external_result_agent_column, s.external_result_payload_column,
            s.external_result_created_column,
        ]
        q = [quote_identifier(column) for column in columns]
        await session.execute(text(f"""
            INSERT INTO {self.result_table}
                ({", ".join(q)})
            VALUES
                (:suggestion_id, :event_id, :status, :confidence, :agent_type,
                 CAST(:payload AS JSONB), :created_at)
            ON CONFLICT ({q[0]}) DO NOTHING
        """), {
            "suggestion_id": suggestion.id,
            "event_id": external_id,
            "status": suggestion.status.value,
            "confidence": suggestion.confidence,
            "agent_type": suggestion.agent_type,
            "payload": payload,
            "created_at": suggestion.created_at,
        })

    async def _update_event(
        self, session: Any, suggestion: Suggestion, external_id: str, payload: str
    ) -> None:
        result_column = quote_identifier(self.settings.external_event_result_column)
        status_column = quote_identifier(self.settings.external_event_result_status_column)
        await session.execute(text(f"""
            UPDATE {self.event_table}
            SET {result_column} = CAST(:payload AS JSONB), {status_column} = :status
            WHERE {self.columns.event_id} = :external_id
        """), {
            "payload": payload,
            "status": suggestion.status.value,
            "external_id": external_id,
        })

    async def close(self) -> None:
        if self.engine is not None:
            await self.engine.dispose()
