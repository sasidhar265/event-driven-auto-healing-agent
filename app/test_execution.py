"""Governed local pytest reruns triggered by accepted suggestions."""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.art_lifecycle import correlation_uuid, event_environment
from app.art_models import ExecutionIntent, ExecutionResultRef, OutcomeFeedback
from app.config import get_settings
from app.models import AuditLog, Event, Outbox, RemediationReference, Suggestion


TEST_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\[[A-Za-z0-9_.:,/+=@-]+\])?$")


def validated_test_target(payload: dict[str, Any]) -> str | None:
    """Return one repository-contained pytest node ID or reject unsafe input."""
    settings = get_settings()
    raw_file = payload.get("test_file")
    raw_name = payload.get("test_name")
    if not isinstance(raw_file, str) or not raw_file.strip():
        return None
    workspace = Path.cwd().resolve()
    allowed_root = (workspace / settings.test_rerun_root).resolve()
    candidate = (workspace / raw_file).resolve()
    try:
        candidate.relative_to(allowed_root)
    except ValueError:
        return None
    if candidate.suffix != ".py" or not candidate.is_file():
        return None
    if raw_name is not None and (
        not isinstance(raw_name, str) or not TEST_NAME.fullmatch(raw_name)
    ):
        return None
    relative = candidate.relative_to(workspace).as_posix()
    return f"{relative}::{raw_name}" if raw_name else relative


async def execute_accepted_suggestion(session: AsyncSession, suggestion_id: uuid.UUID) -> None:
    """Run a validated test target and stage governed result records."""
    suggestion = await session.scalar(select(Suggestion).where(Suggestion.id == suggestion_id))
    if suggestion is None:
        raise ValueError(f"suggestion {suggestion_id} not found")
    event = await session.scalar(select(Event).where(Event.id == suggestion.event_id))
    if event is None:
        raise ValueError(f"event {suggestion.event_id} not found")

    settings = get_settings()
    target = validated_test_target(event.payload) if settings.test_rerun_enabled else None
    correlation_id = correlation_uuid(event)
    environment = event_environment(event)
    intent = ExecutionIntent(
        id=uuid.uuid4(),
        correlation_id=correlation_id,
        tenant_id=event.tenant_id,
        environment=environment,
        execution_target=target or "unavailable",
        execution_mode="LOCAL_PYTEST",
        selected_tests=[target] if target else [],
        constraints={
            "allow_root": settings.test_rerun_root,
            "timeout_seconds": settings.test_rerun_timeout_seconds,
            "shell": False,
        },
        status="IN_PROGRESS" if target else "SKIPPED",
        approval_required=True,
        approval_status="APPROVED",
        dispatched_at=datetime.now(UTC) if target else None,
        evidence_requirements=["accepted suggestion", "allow-listed pytest target"],
    )
    session.add(intent)
    await session.flush()

    if not target:
        requested_file = event.payload.get("test_file")
        requested_name = event.payload.get("test_name")
        result = {
            "status": "SKIPPED",
            "return_code": None,
            "output": (
                "The requested test target is missing or outside the allow-listed "
                f"root '{settings.test_rerun_root}': "
                f"test_file={requested_file!r}, test_name={requested_name!r}."
            ),
        }
    else:
        result = await _run_pytest(target)

    completed_at = datetime.now(UTC)
    intent.status = result["status"]
    intent.completed_at = completed_at
    intent.execution_result_ref = f"audit:suggestion:{suggestion.id}:test-rerun"
    result_ref = ExecutionResultRef(
        id=uuid.uuid4(),
        execution_intent_id=intent.id,
        correlation_id=correlation_id,
        tenant_id=event.tenant_id,
        environment=environment,
        status=result["status"],
        passed_count=1 if result["status"] == "SUCCESS" else 0,
        failed_count=1 if result["status"] == "FAILED" else 0,
        skipped_count=1 if result["status"] == "SKIPPED" else 0,
        failures_summary=(
            [{"target": target, "output": result["output"]}] if result["status"] == "FAILED" else []
        ),
        result_ref=intent.execution_result_ref,
    )
    session.add(result_ref)
    await session.flush()
    reference = await session.scalar(
        select(RemediationReference).where(RemediationReference.suggestion_id == suggestion.id)
    )
    if reference is not None and result["status"] in {"SUCCESS", "FAILED"}:
        reference.active = result["status"] == "SUCCESS"
        reference.outcome = "test_passed" if result["status"] == "SUCCESS" else "test_failed"
        reference.decision_reason = (
            "Accepted remediation passed its governed test rerun."
            if result["status"] == "SUCCESS"
            else "Accepted remediation failed its governed test rerun."
        )

    if result["status"] == "FAILED":
        await _queue_bounded_reanalysis(session, event, suggestion, target, result["output"])
    session.add(
        OutcomeFeedback(
            correlation_id=correlation_id,
            tenant_id=event.tenant_id,
            environment=environment,
            execution_intent_id=intent.id,
            execution_result_ref_id=result_ref.id,
            feedback_type="TEST_RERUN",
            feedback_summary=f"Accepted suggestion test rerun {result['status'].lower()}.",
            test_effectiveness={"target": target, "return_code": result["return_code"]},
            recommended_action=(
                "Review the failing output before applying the remediation."
                if result["status"] == "FAILED"
                else None
            ),
        )
    )
    session.add(
        AuditLog(
            tenant_id=event.tenant_id,
            actor="test-rerun-worker",
            action="suggestion.test_rerun_completed",
            resource_type="suggestion",
            resource_id=str(suggestion.id),
            details={
                "event_id": str(event.id),
                "target": target,
                "status": result["status"],
                "return_code": result["return_code"],
                "output": result["output"],
                "execution_intent_id": str(intent.id),
                "execution_result_id": str(result_ref.id),
            },
        )
    )


async def _queue_bounded_reanalysis(
    session: AsyncSession,
    event: Event,
    suggestion: Suggestion,
    target: str | None,
    output: str,
) -> None:
    """Store negative evidence and request a limited alternative analysis."""
    settings = get_settings()
    attempt = int(event.payload.get("art_reanalysis_attempts", 0)) + 1
    failed = list(event.payload.get("art_failed_suggestions", []))
    failed.append(
        {
            "suggestion_id": str(suggestion.id),
            "title": suggestion.title,
            "agent_type": suggestion.agent_type,
            "test_target": target,
            "failure_output": output[-2000:],
        }
    )
    event.payload = {
        **event.payload,
        "art_reanalysis_attempts": attempt,
        "art_failed_suggestions": failed,
    }
    if attempt <= settings.test_reanalysis_max_attempts:
        session.add(
            Outbox(
                topic="event.reanalysis.requested",
                aggregate_id=event.id,
                payload={
                    "event_id": str(event.id),
                    "failed_suggestion_id": str(suggestion.id),
                    "attempt": attempt,
                },
            )
        )
        action = "event.reanalysis_queued"
        details = {
            "attempt": attempt,
            "maximum_attempts": settings.test_reanalysis_max_attempts,
            "failed_suggestion_id": str(suggestion.id),
        }
    else:
        action = "event.reanalysis_escalated"
        details = {
            "attempt": attempt,
            "maximum_attempts": settings.test_reanalysis_max_attempts,
            "reason": "Automatic alternative-remediation attempts exhausted",
            "human_investigation_required": True,
        }
    session.add(
        AuditLog(
            tenant_id=event.tenant_id,
            actor="test-rerun-worker",
            action=action,
            resource_type="event",
            resource_id=str(event.id),
            details=details,
        )
    )


async def _run_pytest(target: str) -> dict[str, Any]:
    """Invoke pytest without a shell and capture bounded output."""
    settings = get_settings()
    executable = Path(settings.test_rerun_pytest_path)
    if not executable.is_absolute():
        executable = Path.cwd() / executable
    try:
        process = await asyncio.create_subprocess_exec(
            str(executable),
            "-q",
            target,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(
            process.communicate(), timeout=settings.test_rerun_timeout_seconds
        )
        output = stdout.decode("utf-8", errors="replace")[-settings.test_rerun_output_max_length :]
        return {
            "status": "SUCCESS" if process.returncode == 0 else "FAILED",
            "return_code": process.returncode,
            "output": output,
        }
    except TimeoutError:
        process.kill()
        await process.wait()
        return {
            "status": "FAILED",
            "return_code": None,
            "output": f"pytest exceeded {settings.test_rerun_timeout_seconds} seconds",
        }
    except OSError as exc:
        return {"status": "FAILED", "return_code": None, "output": str(exc)}
