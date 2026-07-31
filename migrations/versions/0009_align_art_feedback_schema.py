"""Align ART column types and indexes with ART_Feedback.docx."""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


ENUMS = {
    "art_environment": ("dev", "test", "preprod", "prod"),
    "art_change_type": ("code", "config", "infra", "data", "failure"),
    "art_status": (
        "RECEIVED", "IN_PROGRESS", "SUCCESS", "FAILED", "REQUIRES_APPROVAL",
        "APPROVED", "REJECTED", "EXECUTED", "CANCELLED", "SKIPPED",
    ),
    "art_severity": ("LOW", "MEDIUM", "HIGH", "CRITICAL"),
    "art_failure_category": (
        "UI", "API", "FUNCTIONAL", "DATA", "PERFORMANCE", "SECURITY",
        "BATCH", "MAINFRAME", "INFRA", "UNKNOWN",
    ),
    "art_workflow_type": (
        "CHANGE_ANALYSIS", "FAILURE_ANALYSIS", "IMPACT_ANALYSIS",
        "TEST_SELECTION", "EXECUTION_ORCHESTRATION", "SELF_MAINTENANCE",
    ),
    "art_decision_type": (
        "IMPACT_ASSESSMENT", "TEST_SELECTION", "TEST_SEQUENCING",
        "EXECUTION_INTENT", "SELF_HEAL_PROPOSAL", "OUTCOME_EVALUATION",
    ),
    "art_self_heal_type": (
        "LOCATOR", "TEST_DATA", "ASSERTION", "MINOR_LOGIC", "CONFIG_DEPENDENCY",
    ),
    "art_approval_status": (
        "NOT_REQUIRED", "PENDING", "APPROVED", "REJECTED", "EXPIRED", "CANCELLED",
    ),
}

ENVIRONMENT_TABLES = (
    "failure_events", "agent_runs", "agent_run_steps", "agent_decision_journals",
    "impact_assessments", "impact_dependencies", "test_selection_decisions",
    "execution_intents", "execution_result_refs", "self_heal_proposals",
    "outcome_feedback", "event_inbox", "event_outbox",
)

STATUS_COLUMNS = (
    ("agent_runs", "status", "RECEIVED"),
    ("agent_run_steps", "status", "RECEIVED"),
    ("execution_intents", "status", "RECEIVED"),
    ("execution_result_refs", "status", None),
    ("self_heal_proposals", "applied_status", "RECEIVED"),
    ("event_inbox", "processing_status", "RECEIVED"),
    ("event_outbox", "publish_status", "RECEIVED"),
)

ENUM_COLUMNS = (
    ("failure_events", "failure_category", "art_failure_category", "UNKNOWN"),
    ("failure_events", "severity", "art_severity", "MEDIUM"),
    ("agent_runs", "workflow_type", "art_workflow_type", None),
    ("agent_decision_journals", "decision_type", "art_decision_type", None),
    ("impact_assessments", "impact_source", "art_change_type", None),
    ("impact_assessments", "impact_level", "art_severity", None),
    ("execution_intents", "approval_status", "art_approval_status", "NOT_REQUIRED"),
    ("self_heal_proposals", "proposal_type", "art_self_heal_type", None),
    ("self_heal_proposals", "approval_status", "art_approval_status", "PENDING"),
)

NUMERIC_COLUMNS = (
    ("agent_run_steps", "confidence_score"),
    ("agent_decision_journals", "confidence_score"),
    ("impact_assessments", "risk_score"),
    ("impact_assessments", "confidence_score"),
    ("impact_dependencies", "dependency_confidence"),
    ("test_selection_decisions", "risk_score"),
    ("test_selection_decisions", "confidence_score"),
    ("test_selection_decisions", "risk_coverage"),
    ("self_heal_proposals", "confidence_score"),
)

REQUIREMENT_INDEXES = {
    "idx_failure_events_test": "art.failure_events (test_id)",
    "idx_failure_events_trace": "art.failure_events (trace_id)",
    "idx_agent_runs_status": "art.agent_runs (status)",
    "idx_agent_runs_workflow": "art.agent_runs (workflow_type)",
    "idx_agent_run_steps_run": "art.agent_run_steps (agent_run_id)",
    "idx_agent_run_steps_agent": "art.agent_run_steps (agent_name)",
    "idx_agent_decision_journals_run": "art.agent_decision_journals (agent_run_id)",
    "idx_agent_decision_journals_type": "art.agent_decision_journals (decision_type)",
    "idx_impact_assessments_component": "art.impact_assessments (component_id, component_name)",
    "idx_impact_assessments_capability": "art.impact_assessments (business_capability_id)",
    "idx_impact_assessments_level": "art.impact_assessments (impact_level)",
    "idx_impact_dependencies_impact": "art.impact_dependencies (impact_assessment_id)",
    "idx_impact_dependencies_component": "art.impact_dependencies (dependent_component_id, dependent_component_name)",
    "idx_test_selection_run": "art.test_selection_decisions (agent_run_id)",
    "idx_test_selection_policy": "art.test_selection_decisions (policy_decision_id)",
    "idx_execution_intents_status": "art.execution_intents (status)",
    "idx_execution_intents_external_run": "art.execution_intents (external_run_id)",
    "idx_execution_intents_policy": "art.execution_intents (policy_decision_id)",
    "idx_execution_result_refs_intent": "art.execution_result_refs (execution_intent_id)",
    "idx_execution_result_refs_external_run": "art.execution_result_refs (external_run_id)",
    "idx_self_heal_failure": "art.self_heal_proposals (failure_event_id)",
    "idx_self_heal_approval": "art.self_heal_proposals (approval_status)",
    "idx_self_heal_policy": "art.self_heal_proposals (policy_decision_id)",
    "idx_outcome_feedback_run": "art.outcome_feedback (agent_run_id)",
    "idx_outcome_feedback_type": "art.outcome_feedback (feedback_type)",
    "idx_event_inbox_status": "art.event_inbox (processing_status)",
    "idx_event_outbox_status": "art.event_outbox (publish_status)",
}


def _create_enum(name: str, values: tuple[str, ...]) -> None:
    literals = ", ".join(f"'{value}'" for value in values)
    op.execute(f"CREATE TYPE art.{name} AS ENUM ({literals})")


def _to_enum(table: str, column: str, enum_name: str, default: str | None) -> None:
    op.execute(f"ALTER TABLE art.{table} ALTER COLUMN {column} DROP DEFAULT")
    op.execute(
        f"ALTER TABLE art.{table} ALTER COLUMN {column} "
        f"TYPE art.{enum_name} USING {column}::text::art.{enum_name}"
    )
    if default is not None:
        op.execute(
            f"ALTER TABLE art.{table} ALTER COLUMN {column} "
            f"SET DEFAULT '{default}'::art.{enum_name}"
        )


def _create_views() -> None:
    op.execute("""
        CREATE VIEW art.v_agent_run_summary AS
        SELECT ar.id AS agent_run_id, ar.correlation_id, ar.tenant_id,
          ar.environment, ar.workflow_type, ar.status, ar.started_at,
          ar.completed_at, ar.execution_time_ms, ar.policy_decision_id,
          ar.policy_version, ar.approval_required,
          COUNT(ars.id) AS total_steps,
          COUNT(ars.id) FILTER (WHERE ars.status = 'SUCCESS') AS successful_steps,
          COUNT(ars.id) FILTER (WHERE ars.status = 'FAILED') AS failed_steps
        FROM art.agent_runs ar
        LEFT JOIN art.agent_run_steps ars ON ar.id = ars.agent_run_id
        GROUP BY ar.id
    """)
    op.execute("""
        CREATE VIEW art.v_correlation_trace AS
        SELECT ar.correlation_id, ar.tenant_id, ar.environment, ar.workflow_type,
          ar.status AS agent_run_status,
          tsd.id AS test_selection_decision_id,
          ei.id AS execution_intent_id, ei.status AS execution_status,
          shp.id AS self_heal_proposal_id,
          shp.approval_status AS self_heal_approval_status
        FROM art.agent_runs ar
        LEFT JOIN art.test_selection_decisions tsd
          ON ar.correlation_id = tsd.correlation_id AND ar.tenant_id = tsd.tenant_id
        LEFT JOIN art.execution_intents ei
          ON ar.correlation_id = ei.correlation_id AND ar.tenant_id = ei.tenant_id
        LEFT JOIN art.self_heal_proposals shp
          ON ar.correlation_id = shp.correlation_id AND ar.tenant_id = shp.tenant_id
    """)


def upgrade() -> None:
    op.execute("DROP VIEW art.v_correlation_trace")
    op.execute("DROP VIEW art.v_agent_run_summary")

    for name, values in ENUMS.items():
        _create_enum(name, values)

    for table in ENVIRONMENT_TABLES:
        op.execute(
            f"ALTER TABLE art.{table} DROP CONSTRAINT IF EXISTS {table}_environment_check"
        )
        _to_enum(table, "environment", "art_environment", None)

    for table, column, default in STATUS_COLUMNS:
        _to_enum(table, column, "art_status", default)

    for table, column, enum_name, default in ENUM_COLUMNS:
        op.execute(
            f"ALTER TABLE art.{table} DROP CONSTRAINT IF EXISTS {table}_{column}_check"
        )
        _to_enum(table, column, enum_name, default)

    for table, column in NUMERIC_COLUMNS:
        op.execute(
            f"ALTER TABLE art.{table} ALTER COLUMN {column} "
            f"TYPE NUMERIC(5,4) USING {column}::numeric(5,4)"
        )

    for name, target in REQUIREMENT_INDEXES.items():
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {target}")

    _create_views()


def downgrade() -> None:
    op.execute("DROP VIEW art.v_correlation_trace")
    op.execute("DROP VIEW art.v_agent_run_summary")

    for name in REQUIREMENT_INDEXES:
        op.execute(f"DROP INDEX IF EXISTS art.{name}")

    for table, column in NUMERIC_COLUMNS:
        op.execute(
            f"ALTER TABLE art.{table} ALTER COLUMN {column} "
            f"TYPE DOUBLE PRECISION USING {column}::double precision"
        )

    for table, column, _enum_name, default in reversed(ENUM_COLUMNS):
        op.execute(f"ALTER TABLE art.{table} ALTER COLUMN {column} DROP DEFAULT")
        op.execute(
            f"ALTER TABLE art.{table} ALTER COLUMN {column} "
            f"TYPE VARCHAR USING {column}::text"
        )
        if default is not None:
            op.execute(f"ALTER TABLE art.{table} ALTER COLUMN {column} SET DEFAULT '{default}'")

    for table, column, default in reversed(STATUS_COLUMNS):
        op.execute(f"ALTER TABLE art.{table} ALTER COLUMN {column} DROP DEFAULT")
        op.execute(
            f"ALTER TABLE art.{table} ALTER COLUMN {column} "
            f"TYPE VARCHAR(30) USING {column}::text"
        )
        if default is not None:
            op.execute(f"ALTER TABLE art.{table} ALTER COLUMN {column} SET DEFAULT '{default}'")

    for table in reversed(ENVIRONMENT_TABLES):
        op.execute(
            f"ALTER TABLE art.{table} ALTER COLUMN environment "
            f"TYPE VARCHAR(20) USING environment::text"
        )

    for name in reversed(tuple(ENUMS)):
        op.execute(f"DROP TYPE art.{name}")

    _create_views()
