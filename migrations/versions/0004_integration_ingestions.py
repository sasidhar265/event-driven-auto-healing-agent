"""Track which configured bridge ingested an event."""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS integration_ingestions (
          id UUID PRIMARY KEY,
          event_id UUID NOT NULL REFERENCES events(id),
          source VARCHAR(500) NOT NULL,
          external_id VARCHAR(500) NOT NULL,
          ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CONSTRAINT uq_integration_event_source UNIQUE (event_id, source)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_integration_ingestions_event_id
        ON integration_ingestions (event_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS integration_ingestions")
