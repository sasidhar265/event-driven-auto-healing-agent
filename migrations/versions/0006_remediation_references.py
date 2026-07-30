"""Persist human decisions and reusable remediation references."""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS suggestion_decisions (
          id UUID PRIMARY KEY,
          suggestion_id UUID NOT NULL REFERENCES suggestions(id),
          tenant_id VARCHAR(100) NOT NULL,
          decision VARCHAR(30) NOT NULL,
          reason TEXT NOT NULL,
          actor VARCHAR(200) NOT NULL,
          decided_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CONSTRAINT uq_suggestion_decisions_suggestion UNIQUE (suggestion_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_suggestion_decisions_suggestion_id
        ON suggestion_decisions (suggestion_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_suggestion_decisions_tenant_id
        ON suggestion_decisions (tenant_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_suggestion_decisions_tenant_decided
        ON suggestion_decisions (tenant_id, decided_at)
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS remediation_references (
          id UUID PRIMARY KEY,
          event_id UUID NOT NULL REFERENCES events(id),
          suggestion_id UUID NOT NULL REFERENCES suggestions(id),
          tenant_id VARCHAR(100) NOT NULL,
          event_type VARCHAR(150) NOT NULL,
          severity VARCHAR(30) NOT NULL,
          fingerprint VARCHAR(64) NOT NULL,
          agent_type VARCHAR(50) NOT NULL,
          title VARCHAR(250) NOT NULL,
          rationale TEXT NOT NULL,
          proposed_changes JSONB NOT NULL,
          evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
          confidence DOUBLE PRECISION NOT NULL,
          outcome VARCHAR(30) NOT NULL,
          decision_reason TEXT NOT NULL,
          active BOOLEAN NOT NULL DEFAULT FALSE,
          use_count INTEGER NOT NULL DEFAULT 0,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          last_used_at TIMESTAMPTZ,
          CONSTRAINT uq_remediation_reference_suggestion UNIQUE (suggestion_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_remediation_references_event_id
        ON remediation_references (event_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_remediation_references_suggestion_id
        ON remediation_references (suggestion_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_remediation_references_tenant_id
        ON remediation_references (tenant_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_remediation_references_fingerprint
        ON remediation_references (fingerprint)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_remediation_reference_tenant_active_type
        ON remediation_references (tenant_id, active, event_type)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS remediation_references")
    op.execute("DROP TABLE IF EXISTS suggestion_decisions")
