"""Database operations shared by the ART lifecycle API routes."""

import uuid
from datetime import UTC, datetime
from typing import Any, TypeVar

from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import DeclarativeBase

from app.art_models import (
    AgentRun,
    AgentRunStep,
    ExecutionIntent,
    ExecutionResultRef,
    FailureEvent,
    ImpactAssessment,
    SelfHealProposal,
    TestSelectionDecision,
)
from app.art_schemas import ArtResourceResponse, LifecycleStateUpdate
from app.models import AuditLog
from app.security import Principal

ArtModel = TypeVar("ArtModel", bound=DeclarativeBase)

PARENT_REFERENCES = (
    ("agent_run_id", AgentRun),
    ("agent_step_id", AgentRunStep),
    ("impact_assessment_id", ImpactAssessment),
    ("test_selection_decision_id", TestSelectionDecision),
    ("execution_intent_id", ExecutionIntent),
    ("execution_result_ref_id", ExecutionResultRef),
    ("failure_event_id", FailureEvent),
)

GOVERNED_RESOURCES = {ExecutionIntent, SelfHealProposal}
GOVERNED_STATES = {"APPROVED", "EXECUTED"}
STATUS_FIELDS = ("status", "processing_status", "publish_status", "applied_status")
TIMESTAMP_FIELDS = ("created_at", "received_at", "requested_at")


class ArtRepository:
    """Read and write tenant-scoped ART lifecycle records."""

    def __init__(self, session: AsyncSession, principal: Principal):
        """Bind repository operations to one transaction and tenant principal."""
        self.session = session
        self.principal = principal

    async def create(
        self,
        model: type[ArtModel],
        body: BaseModel,
    ) -> ArtResourceResponse:
        """Validate, persist, audit, and return one lifecycle resource."""
        await self._validate_parent_references(body)

        record = model(
            tenant_id=self.principal.tenant_id,
            **body.model_dump(),
        )
        self.session.add(record)
        await self.session.flush()

        self._add_audit_entry(
            record,
            action="created",
            details={
                "correlation_id": str(record.correlation_id),
                "environment": record.environment,
                "status": self._status_of(record),
            },
        )
        await self.session.commit()
        await self.session.refresh(record)
        return self._as_response(record)

    async def list(
        self,
        model: type[ArtModel],
        *,
        correlation_id: uuid.UUID | None,
        environment: str | None,
        limit: int,
    ) -> list[ArtResourceResponse]:
        """List tenant resources with optional correlation/environment filters."""
        query = select(model).where(model.tenant_id == self.principal.tenant_id)
        if correlation_id is not None:
            query = query.where(model.correlation_id == correlation_id)
        if environment is not None:
            query = query.where(model.environment == environment)

        timestamp = self._timestamp_column(model)
        records = (await self.session.scalars(query.order_by(timestamp.desc()).limit(limit))).all()
        return [self._as_response(record) for record in records]

    async def get(
        self,
        model: type[ArtModel],
        record_id: uuid.UUID,
    ) -> ArtResourceResponse:
        """Return one tenant-owned lifecycle resource or raise HTTP 404."""
        return self._as_response(await self._find(model, record_id))

    async def change_state(
        self,
        model: type[ArtModel],
        record_id: uuid.UUID,
        update: LifecycleStateUpdate,
    ) -> ArtResourceResponse:
        """Apply and audit a valid lifecycle state change."""
        record = await self._find(model, record_id)
        changes = update.model_dump(exclude_none=True)
        requested_status = changes.pop("status")

        policy_decision_id = changes.get("policy_decision_id") or getattr(
            record,
            "policy_decision_id",
            None,
        )
        if (
            model in GOVERNED_RESOURCES
            and requested_status in GOVERNED_STATES
            and policy_decision_id is None
        ):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "A governance policy_decision_id is required for this state transition",
            )

        status_field = self._status_field(record)
        setattr(record, status_field, requested_status)
        for field, value in changes.items():
            if hasattr(record, field):
                setattr(record, field, value)

        self._add_audit_entry(
            record,
            action="state_changed",
            details={"status": self._status_of(record)},
        )
        await self.session.commit()
        await self.session.refresh(record)
        return self._as_response(record)

    async def correlation_trace(self, correlation_id: uuid.UUID) -> dict[str, Any]:
        """Read the tenant-scoped lifecycle reporting view for a correlation ID."""
        result = await self.session.execute(
            text("""
                SELECT *
                FROM art.v_correlation_trace
                WHERE correlation_id = :correlation_id
                  AND tenant_id = :tenant_id
            """),
            {
                "correlation_id": correlation_id,
                "tenant_id": self.principal.tenant_id,
            },
        )
        return {
            "correlation_id": correlation_id,
            "tenant_id": self.principal.tenant_id,
            "records": [dict(row) for row in result.mappings().all()],
        }

    async def _find(
        self,
        model: type[ArtModel],
        record_id: uuid.UUID,
    ) -> ArtModel:
        """Find one tenant-owned model instance or raise HTTP 404."""
        record = await self.session.scalar(
            select(model).where(
                model.id == record_id,
                model.tenant_id == self.principal.tenant_id,
            )
        )
        if record is None:
            readable_name = model.__name__.replace("_", " ")
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                f"{readable_name} not found",
            )
        return record

    async def _validate_parent_references(self, body: BaseModel) -> None:
        """Ensure every supplied lifecycle parent belongs to this tenant."""
        for field, model in PARENT_REFERENCES:
            record_id = getattr(body, field, None)
            if record_id is not None:
                await self._find(model, record_id)

    def _add_audit_entry(
        self,
        record: DeclarativeBase,
        *,
        action: str,
        details: dict[str, Any],
    ) -> None:
        """Stage a lifecycle audit entry in the current transaction."""
        resource_name = f"art.{record.__tablename__}"
        self.session.add(
            AuditLog(
                tenant_id=self.principal.tenant_id,
                actor=self.principal.actor,
                action=f"{resource_name}.{action}",
                resource_type=resource_name,
                resource_id=str(record.id),
                details=details,
            )
        )

    @staticmethod
    def _as_response(record: DeclarativeBase) -> ArtResourceResponse:
        """Normalize any ART model into the common API response contract."""
        values = {
            column.key: getattr(record, column.key) for column in inspect(type(record)).columns
        }
        created_at = next(
            (
                value
                for field in TIMESTAMP_FIELDS
                if (value := getattr(record, field, None)) is not None
            ),
            datetime.now(UTC),
        )
        return ArtResourceResponse(
            resource_id=record.id,
            correlation_id=record.correlation_id,
            tenant_id=record.tenant_id,
            environment=record.environment,
            status=ArtRepository._status_of(record),
            created_at=created_at,
            updated_at=getattr(record, "updated_at", None),
            data=values,
        )

    @staticmethod
    def _status_field(record: DeclarativeBase) -> str:
        """Return the model-specific lifecycle status attribute name."""
        for field in STATUS_FIELDS:
            if hasattr(record, field):
                return field
        raise ValueError(f"{type(record).__name__} has no lifecycle status field")

    @staticmethod
    def _status_of(record: DeclarativeBase) -> str:
        """Return a normalized status string for any lifecycle record."""
        for field in STATUS_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                return value.value if hasattr(value, "value") else str(value)
        return "RECORDED"

    @staticmethod
    def _timestamp_column(model: type[ArtModel]):
        """Return the best model timestamp column for newest-first ordering."""
        for field in TIMESTAMP_FIELDS:
            column = getattr(model, field, None)
            if column is not None:
                return column
        raise ValueError(f"{model.__name__} has no lifecycle timestamp")
