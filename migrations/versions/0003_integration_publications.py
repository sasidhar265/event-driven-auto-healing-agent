"""Track publication to configurable external integrations."""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS integration_publications (
          id UUID PRIMARY KEY,
          suggestion_id UUID NOT NULL REFERENCES suggestions(id),
          target VARCHAR(500) NOT NULL,
          published_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CONSTRAINT uq_integration_suggestion_target
            UNIQUE (suggestion_id, target)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_integration_publications_suggestion_id
        ON integration_publications (suggestion_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS integration_publications")
