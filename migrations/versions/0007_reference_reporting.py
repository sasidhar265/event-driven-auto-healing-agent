"""Expose remediation learning history to pgAdmin."""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE VIEW art_reporting.reference_library AS
        SELECT
          rr.id AS reference_id,
          rr.tenant_id,
          rr.event_type,
          rr.severity,
          rr.fingerprint,
          rr.agent_type,
          rr.title,
          rr.confidence,
          rr.outcome,
          rr.active,
          rr.decision_reason,
          sd.actor AS decided_by,
          sd.decided_at,
          rr.use_count,
          rr.last_used_at,
          rr.proposed_changes,
          rr.evidence,
          rr.event_id,
          rr.suggestion_id
        FROM remediation_references rr
        JOIN suggestion_decisions sd ON sd.suggestion_id = rr.suggestion_id
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS art_reporting.reference_library")
